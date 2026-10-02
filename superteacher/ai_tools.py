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
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from . import metrics
from .models import Student
from .queries import load_students

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


def student_block(s: Student, m: metrics.StudentMetrics, max_scores: int | None = None, max_notes: int = 5) -> str:
    lines = [student_line(s, m)]
    if m.risk_reasons:
        lines.append("  flags: " + "; ".join(m.risk_reasons))
    lines.append(f"  absences {m.absences}, tardies {m.tardies}")
    scores = m.scores if max_scores is None else m.scores[-max_scores:]
    for p in scores:
        got = "MISSING" if p.points is None else f"{p.points:g}/{p.max_points:g}"
        lines.append(f"  · {p.due_date} {p.kind.value} {clean(p.title, 80)}: {got}")
    for n in s.notes[:max_notes]:
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
                "risk": {"type": "string", "enum": ["on_track", "watch", "at_risk"]},
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
            "for the whole class, or one section/course when `section` is given."
        ),
        "input_schema": {"type": "object", "properties": {"section": {"type": "string"}}},
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class FindStudentsArgs(BaseModel):
    section: str | None = Field(None, max_length=80)
    risk: Literal["on_track", "watch", "at_risk"] | None = None
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
    rows = []
    for s in students:
        if not _in_section(s, a.section) or (a.name_contains and a.name_contains.lower() not in s.name.lower()):
            continue
        m = metrics.compute(s)
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
        rows.append((s, m))
    keyf: dict[str, Callable] = {
        "name": lambda sm: sm[0].name.lower(),
        "average": lambda sm: sm[1].average,
        "attendance": lambda sm: sm[1].attendance_rate,
        "trend": lambda sm: sm[1].trend,
        "missing": lambda sm: sm[1].missing,
    }
    k = keyf[a.sort_by]
    have = [x for x in rows if k(x) is not None]  # unknowns sort last regardless of direction
    rows = sorted(have, key=k, reverse=a.descending) + [x for x in rows if k(x) is None]
    limit = min(a.limit, 25)
    return {
        "total_matches": len(rows),
        "returned": min(limit, len(rows)),
        "students": [_row(s, m) for s, m in rows[:limit]],
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
    pool = [(s, metrics.compute(s)) for s in students if _in_section(s, a.section)]
    if not pool:
        return {"error": "No students in that section."}

    def avg(vals):
        value = metrics.mean_of(vals)
        return None if value is None else round(value, 1)

    out: dict[str, Any] = {
        "students": len(pool),
        "average": avg(m.average for _, m in pool),
        "attendance": avg(m.attendance_rate for _, m in pool),
        "homework": avg(m.homework_rate for _, m in pool),
        "missing_assignments": sum(m.missing for _, m in pool),
        "status_counts": dict(Counter(m.risk for _, m in pool)),
        "letter_distribution": dict(Counter(m.letter or "n/a" for _, m in pool)),
    }
    if not a.section:
        by_sec: dict[str, list[metrics.StudentMetrics]] = {}
        for s, m in pool:
            by_sec.setdefault(section_label(s), []).append(m)
        out["sections"] = [
            {
                "section": k,
                "students": len(v),
                "average": avg(x.average for x in v),
                "at_risk": sum(x.risk == "at_risk" for x in v),
            }
            for k, v in sorted(by_sec.items())
        ]
    return out


_HANDLERS: dict[str, tuple[type[BaseModel], Callable]] = {
    "find_students": (FindStudentsArgs, find_students),
    "get_student": (GetStudentArgs, get_student),
    "class_stats": (ClassStatsArgs, class_stats),
}


class ToolError(Exception):
    """Raised for bad tool name/arguments; the message is safe to show the model."""


def execute(db: Session, name: str, raw_input: object) -> str:
    """Run one tool and return the string for the tool_result block (always bounded in size)."""
    if name not in _HANDLERS:
        raise ToolError(f"Unknown tool {name!r}.")
    model, fn = _HANDLERS[name]
    try:
        args = model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as e:
        raise ToolError(
            "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        ) from None
    result = fn(load_students(db), args)
    text = result if isinstance(result, str) else json.dumps(result, separators=(",", ":"), default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "\n[truncated]"
    return text
