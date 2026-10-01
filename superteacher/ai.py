"""Claude integration: server-built context, streaming chat, and per-student insight cards.

The model never sees scraped page text. It sees a compact, structured snapshot of
the teacher's actual roster, built from the same metrics the UI shows.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from anthropic import AsyncAnthropic
from sqlalchemy.orm import Session

from . import metrics, schemas
from .config import get_settings
from .models import InsightCache, Student

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Super Teacher, a teaching partner for a K-12 classroom teacher.
You are given a live snapshot of their roster (grades, trends, attendance, homework, notes).

How to respond:
- Ground every claim in the snapshot. Name students and quote numbers. If the data cannot answer, say so.
- Be concise: lead with the answer, then the 2-4 things that matter. Use short markdown lists or tables.
- Suggest concrete next steps a teacher can do this week (a conversation, a regroup, a parent check-in),
  not generic advice.
- Treat student data as confidential. Never speculate about home life, diagnoses or disability; describe
  patterns in the work and attendance only, and recommend the teacher follow school procedures for concerns.
- You advise; the teacher decides."""


def client() -> AsyncAnthropic | None:
    key = get_settings().anthropic_api_key
    return AsyncAnthropic(api_key=key) if key else None


def _fmt(v: float | None, suffix: str = "") -> str:
    return "n/a" if v is None else f"{v:.0f}{suffix}"


def student_line(s: Student, m: metrics.StudentMetrics) -> str:
    trend = "n/a" if m.trend is None else f"{m.trend:+.0f}"
    return (
        f"- {s.name} (id {s.id}, gr {s.grade_level}, {s.section.course.name} / {s.section.name}): "
        f"avg {_fmt(m.average, '%')} {m.letter or ''}, trend {trend}, attendance {_fmt(m.attendance_rate, '%')}, "
        f"homework {_fmt(m.homework_rate, '%')}, missing {m.missing}, status {m.risk}"
    )


def student_block(s: Student, m: metrics.StudentMetrics) -> str:
    lines = [student_line(s, m)]
    if m.risk_reasons:
        lines.append("  flags: " + "; ".join(m.risk_reasons))
    lines.append(f"  absences {m.absences}, tardies {m.tardies}")
    for p in m.scores:
        got = "MISSING" if p.points is None else f"{p.points:g}/{p.max_points:g}"
        lines.append(f"  · {p.due_date} {p.kind.value} {p.title}: {got}")
    for n in s.notes[:5]:
        lines.append(f"  note ({n.created_at:%Y-%m-%d}): {n.body}")
    return "\n".join(lines)


def build_context(db: Session, student_id: str | None = None) -> str:
    from .routers.roster import load_students  # local import: avoids a router<->ai cycle

    students = load_students(db)
    computed = {s.id: metrics.compute(s) for s in students}
    out = [f"Today is {datetime.now(UTC):%Y-%m-%d}. Roster snapshot ({len(students)} students):"]
    out += [student_line(s, computed[s.id]) for s in students]
    if student_id and (focus := next((s for s in students if s.id == student_id), None)):
        out += ["", f"The teacher is currently viewing {focus.name}. Full record:", student_block(focus, computed[focus.id])]
    return "\n".join(out)


async def stream_chat(history: list[dict], context: str) -> AsyncIterator[str]:
    ai = client()
    if ai is None:
        yield "AI is not configured on this server (set `ANTHROPIC_API_KEY`). The rest of the app works without it."
        return
    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        # The roster snapshot is large and stable across turns → cache it.
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]
    async with ai.messages.stream(
        model=get_settings().anthropic_model, max_tokens=1500, system=system, messages=history
    ) as stream:
        async for text in stream.text_stream:
            yield text


# ── insights ────────────────────────────────────────────────────────────
def rule_insight(s: Student, m: metrics.StudentMetrics) -> schemas.Insight:
    strengths, concerns, actions = [], list(m.risk_reasons), []
    if m.average is not None and m.average >= 85:
        strengths.append(f"Strong average of {m.average:.0f}%")
    if m.trend is not None and m.trend >= 5:
        strengths.append(f"Improving: recent work is {m.trend:.0f} points above earlier work")
    if m.attendance_rate is not None and m.attendance_rate >= 95:
        strengths.append("Excellent attendance")
    if m.homework_rate is not None and m.homework_rate >= 90:
        strengths.append("Consistent homework completion")
    if m.missing:
        concerns.append(f"{m.missing} missing assignment(s)")
        actions.append("Agree a catch-up plan for the missing work")
    if m.average is not None and m.average < 75:
        actions.append("Short check-in on which topics are blocking progress; consider a small-group reteach")
    if m.attendance_rate is not None and m.attendance_rate < 90:
        actions.append("Reach out about attendance before it affects more grades")
    if m.risk == "on_track" and not actions:
        actions.append("Offer an extension or stretch task to keep them engaged")
    headline = {
        "at_risk": f"{s.name} needs support now",
        "watch": f"{s.name} is worth keeping an eye on",
        "on_track": f"{s.name} is on track",
    }[m.risk]
    return schemas.Insight(headline=headline, strengths=strengths, concerns=concerns, actions=actions, source="rules")


INSIGHT_PROMPT = """Write a brief insight card for this student for their teacher. Respond with ONLY a JSON object:
{"headline": str (<=12 words), "strengths": [str], "concerns": [str], "actions": [str]}
Max 3 items per list; each item one short sentence grounded in the data. Actions must be things the teacher can do this week.
Do not speculate about causes outside school.

"""


async def ai_insight(db: Session, s: Student) -> schemas.Insight:
    m = metrics.compute(s)
    fp = metrics.fingerprint(s, m)
    cached = db.get(InsightCache, s.id)
    if cached and cached.fingerprint == fp:
        return schemas.Insight(**cached.payload, source="ai", model=cached.model, generated_at=cached.created_at)

    ai = client()
    if ai is None:
        return rule_insight(s, m)
    model = get_settings().anthropic_insight_model
    try:
        resp = await ai.messages.create(
            model=model, max_tokens=600,
            messages=[{"role": "user", "content": INSIGHT_PROMPT + student_block(s, m)}],
        )  # fmt: skip
        text = resp.content[0].text
        payload = json.loads(text[text.index("{") : text.rindex("}") + 1])
        payload = {k: payload[k] for k in ("headline", "strengths", "concerns", "actions")}
    except Exception:  # noqa: BLE001 — never let a flaky model call break the student page
        log.exception("insight generation failed; falling back to rules")
        return rule_insight(s, m)

    if cached:
        cached.fingerprint, cached.model, cached.payload = fp, model, payload
        cached.created_at = datetime.now(UTC)
    else:
        db.add(InsightCache(student_id=s.id, fingerprint=fp, model=model, payload=payload))
    db.commit()
    return schemas.Insight(**payload, source="ai", model=model, generated_at=datetime.now(UTC))
