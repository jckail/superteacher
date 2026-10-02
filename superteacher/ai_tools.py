"""Server-side tools the chat model can call, plus the untrusted-text helpers they share.

Everything here reads through the same ``metrics`` module as the UI, so tool answers can never
disagree with what the teacher sees. All free text that originates from users (student names,
notes, course/section names, assignment titles) goes through :func:`clean` before reaching the
model so it cannot forge structural tags.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from fractions import Fraction
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import metrics
from .models import OWNER_ID, Course, Note, Section, Student
from .queries import iter_summaries, student_candidates, summaries_for

MAX_TOOL_RESULT_CHARS = 12_000
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")  # C0, DEL and C1 (incl. NEL \x85)


def section_label(s: Student) -> str:
    """'Course / Section' with untrusted names defanged, for prompts and tool results."""
    return f"{clean(s.section.course.name, 60)} / {clean(s.section.name, 40)}"


def clean(text: object, limit: int = 300) -> str:
    """Neutralise untrusted text: strip control chars, defang angle brackets, truncate."""
    # The look-alike quotes are deliberate: they keep the text readable while making it unable to close our tags.
    # NFKC folds full-width/compat brackets to ASCII first so they are defanged too; format characters (zero-width,
    # bidi overrides, Unicode "tag" characters that can smuggle invisible text) are dropped, line/paragraph
    # separators become spaces.
    folded = unicodedata.normalize("NFKC", str(text))
    folded = "".join(
        "" if (cat := unicodedata.category(ch)) == "Cf" else " " if cat in ("Zl", "Zp") else ch for ch in folded
    )
    s = _CTRL.sub(" ", folded).replace("<", "\u2039").replace(">", "\u203a")
    s = re.sub(r" {2,}", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ── rendering ───────────────────────────────────────────────────────────
def _fmt(v: float | None, suffix: str = "") -> str:
    return "n/a" if v is None else f"{v:.0f}{suffix}"


def student_line(s: Student, m: metrics.StudentMetrics) -> str:
    trend = "n/a" if m.trend is None else f"{m.trend:+.0f}"
    return (
        f"- {clean(s.name, 80)} (id {s.id}, gr {s.grade_level}, "
        f"{clean(s.section.course.name, 60)} / {clean(s.section.name, 40)}): "
        f"avg {_fmt(m.average, '%')} {m.letter or ''}, trend {trend}, attendance {_fmt(m.attendance_rate, '%')}, "
        f"homework {_fmt(m.homework_rate, '%')}, missing {m.missing}, status {m.risk}"
    )


def student_block(
    s: Student,
    m: metrics.StudentMetrics,
    max_scores: int | None = None,
    max_notes: int = 5,
    notes: list[Note] | None = None,
) -> str:
    lines = [student_line(s, m)]
    if m.risk_reasons:
        lines.append("  flags: " + "; ".join(m.risk_reasons))
    lines.append(f"  absences {m.absences}, tardies {m.tardies}")
    scores = m.scores if max_scores is None else m.scores[-max_scores:]
    for p in scores:
        got = (
            ("NOT YET DUE" if p.due_date > m.as_of else "MISSING")
            if p.points is None
            else (f"{p.points:g}/{p.max_points:g}")
        )
        lines.append(f"  · {p.due_date} {p.kind.value} {clean(p.title, 80)}: {got}")
    for n in s.notes[:max_notes] if notes is None else notes[:max_notes]:
        lines.append(f'  <note date="{n.created_at:%Y-%m-%d}">{clean(n.body, 400)}</note>')
    return "\n".join(lines)


# ── tool schemas (what the model sees) ──────────────────────────────────
TOOLS: list[dict[str, Any]] = [
    {
        "name": "find_students",
        "description": (
            "Search and rank students using exact, current data. Use for questions like 'who is failing', "
            "'lowest attendance in Period 3', 'students with 3+ missing assignments'. Returns at most 25 rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Case-insensitive substring of a section or course name."},
                "risk": {"type": "string", "enum": ["unknown", "on_track", "watch", "at_risk"],
                         "description": "Unknown: insufficient evidence. Attention flags: watch/at_risk."},
                "name_contains": {"type": "string"},
                "max_average": {"type": "number", "description": "Only students with average <= this (0-100)."},
                "min_average": {"type": "number"},
                "max_attendance": {"type": "number", "description": "Only attendance rate <= this (0-100)."},
                "min_missing": {
                    "type": "integer",
                    "description": "Only students with at least this many missing assignments.",
                },
                "sort_by": {"type": "string", "enum": ["name", "average", "attendance", "trend", "missing"]},
                "descending": {"type": "boolean"},
                "limit": {"type": "integer", "description": "Default 15, max 25."},
            },
        },
    },
    {
        "name": "get_student",
        "description": (
            "Full record for one student: metrics, flags, recent assignments and teacher notes. "
            "Pass student_id (from the roster or find_students) or a name fragment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"student_id": {"type": "string"}, "name": {"type": "string"}},
        },
    },
    {
        "name": "class_stats",
        "description": (
            "Aggregate statistics (average, attendance, homework, risk counts, letter-grade distribution) "
            "for the whole class, or one section/course when `section` is given. "
            "Unknown is insufficient evidence, separate from watch/at_risk attention flags."
        ),
        "input_schema": {"type": "object", "properties": {"section": {"type": "string"}}},
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class FindStudentsArgs(BaseModel):
    section: str | None = Field(None, max_length=80)
    risk: Literal["unknown", "on_track", "watch", "at_risk"] | None = None
    name_contains: str | None = Field(None, max_length=80)
    max_average: float | None = None
    min_average: float | None = None
    max_attendance: float | None = None
    min_missing: int | None = Field(None, ge=0)
    sort_by: Literal["name", "average", "attendance", "trend", "missing"] = "name"
    descending: bool = False
    limit: int = Field(15, ge=1)


class GetStudentArgs(BaseModel):
    student_id: str | None = Field(None, max_length=40)
    name: str | None = Field(None, max_length=80)


class ClassStatsArgs(BaseModel):
    section: str | None = Field(None, max_length=80)


def _in_section(s: Student, frag: str | None) -> bool:
    if not frag:
        return True
    f = frag.lower()
    return f in s.section.name.lower() or f in s.section.course.name.lower()


def _row(s: Student, m: metrics.StudentMetrics) -> dict[str, Any]:
    r = lambda v: None if v is None else round(v, 1)  # noqa: E731
    return {
        "id": s.id, "name": clean(s.name, 80), "grade": s.grade_level,
        "course": clean(s.section.course.name, 60), "section": clean(s.section.name, 40),
        "average": r(m.average), "letter": m.letter, "trend": r(m.trend),
        "attendance": r(m.attendance_rate), "homework": r(m.homework_rate),
        "missing": m.missing, "status": m.risk, "flags": [clean(x, 120) for x in m.risk_reasons],
    }  # fmt: skip


def find_students(students: list[Student], a: FindStudentsArgs) -> dict[str, Any]:
    return _find_summaries(((s, metrics.compute(s)) for s in students), a)


def _find_summaries(summaries: Iterable[tuple[Student, metrics.StudentMetrics]], a: FindStudentsArgs) -> dict[str, Any]:
    rows = []
    total = 0
    limit = min(a.limit, 25)
    keyf: dict[str, Callable] = {
        "name": lambda sm: sm[0].name.lower(),
        "average": lambda sm: sm[1].average,
        "attendance": lambda sm: sm[1].attendance_rate,
        "trend": lambda sm: sm[1].trend,
        "missing": lambda sm: sm[1].missing,
    }
    k = keyf[a.sort_by]
    for s, m in summaries:
        if not _in_section(s, a.section) or (a.name_contains and a.name_contains.lower() not in s.name.lower()):
            continue
        if a.risk and m.risk != a.risk:
            continue
        if (a.max_average is not None and (m.average is None or m.average > a.max_average)) or (
            a.min_average is not None and (m.average is None or m.average < a.min_average)
        ):
            continue
        if a.max_attendance is not None and (m.attendance_rate is None or m.attendance_rate > a.max_attendance):
            continue
        if a.min_missing is not None and m.missing < a.min_missing:
            continue
        total += 1
        rows.append((s, m))
        # Stable bounded ranking: retain at most 25 metrics, including when every student matches.
        have = [x for x in rows if k(x) is not None]
        rows = (sorted(have, key=k, reverse=a.descending) + [x for x in rows if k(x) is None])[:limit]
    return {
        "total_matches": total,
        "returned": len(rows),
        "students": [_row(s, m) for s, m in rows],
    }


def get_student(students: list[Student], a: GetStudentArgs) -> dict[str, Any] | str:
    if a.student_id:
        hits = [s for s in students if s.id == a.student_id]
    elif a.name:
        hits = [s for s in students if a.name.lower() in s.name.lower()]
    else:
        return {"error": "Provide student_id or name."}
    if not hits:
        return {"error": "No matching student."}
    if len(hits) > 1:
        return {
            "error": "Several students match; call again with student_id.",
            "candidates": [_row(s, metrics.compute(s)) for s in hits[:10]],
        }
    s = hits[0]
    return "<student_record>\n" + student_block(s, metrics.compute(s), max_scores=15) + "\n</student_record>"


def class_stats(students: list[Student], a: ClassStatsArgs) -> dict[str, Any]:
    return _class_summaries(((s, metrics.compute(s)) for s in students), a)


class _Mean:
    """Exact float summation matches statistics.mean without retaining the input values."""

    def __init__(self):
        self.total = Fraction()
        self.count = 0

    def add(self, value):
        if value is not None:
            self.total += Fraction(value)
            self.count += 1

    def value(self):
        return None if not self.count else round(float(self.total / self.count), 1)


def _class_summaries(summaries: Iterable[tuple[Student, metrics.StudentMetrics]], a: ClassStatsArgs) -> dict[str, Any]:
    averages, attendance, homework = _Mean(), _Mean(), _Mean()
    count = missing = 0
    statuses = Counter({"unknown": 0, "on_track": 0, "watch": 0, "at_risk": 0})
    letters = Counter()
    sections = {}
    for s, m in summaries:
        if not _in_section(s, a.section):
            continue
        count += 1
        missing += m.missing
        averages.add(m.average)
        attendance.add(m.attendance_rate)
        homework.add(m.homework_rate)
        statuses[m.risk] += 1
        letters[m.letter or "n/a"] += 1
        if not a.section:
            label = section_label(s)
            if label not in sections:
                sections[label] = [0, _Mean(), Counter({"unknown": 0, "on_track": 0, "watch": 0, "at_risk": 0})]
            sec = sections[label]
            sec[0] += 1
            sec[1].add(m.average)
            sec[2][m.risk] += 1
    if not count:
        return {"error": "No students in that section."}
    out = {
        "students": count,
        "average": averages.value(),
        "attendance": attendance.value(),
        "homework": homework.value(),
        "missing_assignments": missing,
        "status_counts": dict(statuses),
        "letter_distribution": dict(letters),
    }
    if not a.section:
        out["sections"] = [
            {"section": label, "students": sec[0], "average": sec[1].value(), "at_risk": sec[2]["at_risk"],
             "unknown": sec[2]["unknown"], "status_counts": dict(sec[2])}
            for label, sec in sorted(sections.items())
        ]
    return out


def _get_student(db: Session, args: GetStudentArgs, owner_id: str):
    if not args.student_id and not args.name:
        return {"error": "Provide student_id or name."}
    hits = student_candidates(
        db, owner_id=owner_id, student_id=args.student_id, name_contains=None if args.student_id else args.name
    )
    if not hits:
        return {"error": "No matching student."}
    if len(hits) > 1:
        return {
            "error": "Several students match; call again with student_id.",
            "candidates": [_row(s, m) for s, m in summaries_for(db, hits, owner_id=owner_id, retain_scores=False)],
        }
    s, m = next(summaries_for(db, hits, owner_id=owner_id))
    notes = list(
        db.scalars(
            select(Note)
            .join(Student)
            .join(Section)
            .join(Course)
            .where(Note.student_id == s.id, Course.owner_id == owner_id)
            .order_by(Note.created_at.desc(), Note.id.desc())
            .limit(5)
        )
    )
    return "<student_record>\n" + student_block(s, m, max_scores=15, notes=notes) + "\n</student_record>"


_HANDLERS: dict[str, tuple[type[BaseModel], Callable]] = {
    "find_students": (FindStudentsArgs, find_students),
    "get_student": (GetStudentArgs, get_student),
    "class_stats": (ClassStatsArgs, class_stats),
}


class ToolError(Exception):
    """Raised for bad tool name/arguments; the message is safe to show the model."""


def execute(db: Session, name: str, raw_input: object, *owner_input: object, owner_id: str = OWNER_ID) -> str:
    """Run one tool and return the string for the tool_result block (always bounded in size)."""
    if owner_input:
        if len(owner_input) != 1:
            raise TypeError("Expected owner, tool name and arguments")
        owner_id, name, raw_input = name, raw_input, owner_input[0]
    if name not in _HANDLERS:
        raise ToolError(f"Unknown tool {name!r}.")
    model, _ = _HANDLERS[name]
    try:
        args = model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as e:
        raise ToolError(
            "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        ) from None
    if name == "get_student":
        result = _get_student(db, args, owner_id)
    elif name == "find_students":
        result = _find_summaries(
            iter_summaries(
                db, owner_id=owner_id, section=args.section, name_contains=args.name_contains, retain_scores=False
            ),
            args,
        )
    else:
        result = _class_summaries(
            iter_summaries(db, owner_id=owner_id, section=args.section, retain_scores=False), args
        )
    text = result if isinstance(result, str) else json.dumps(result, separators=(",", ":"), default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "\n[truncated]"
    return text
