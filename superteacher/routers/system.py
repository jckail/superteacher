from bisect import bisect_right

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import metrics, schemas
from ..accounts import CurrentUser
from ..auth import current_user
from ..calendar import school_timezone, school_today
from ..db import get_db
from ..queries import iter_summaries
from .roster import summarize

router = APIRouter(tags=["system"])


@router.get("/overview", response_model=schemas.Overview)
def overview(
    course_id: str | None = None,
    section_id: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    rows = iter_summaries(db, user.id, retain_scores=False, course_id=course_id, section_id=section_id)
    students = 0
    averages, attendance_rates, homework_rates = [], [], []
    risks = dict.fromkeys(("at_risk", "watch", "on_track", "unknown"), 0)
    bands = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    order = {"at_risk": 0, "watch": 1}
    attention = []
    try:
        for ordinal, (student, m) in enumerate(rows):
            students += 1
            risks[m.risk] += 1
            averages.append(m.average)
            attendance_rates.append(m.attendance_rate)
            homework_rates.append(m.homework_rate)
            if m.letter:
                bands[m.letter[0]] += 1
            if m.risk in order:
                # Ordinal preserves the iterator's raw database name/id order for ties.
                key = (order[m.risk], m.average if m.average is not None else 101, ordinal)
                position = bisect_right(attention, key, key=lambda item: item[0])
                if position < 8:
                    if len(attention) == 8:
                        attention.pop()
                    attention.insert(position, (key, student, m))
    finally:
        rows.close()
    return schemas.Overview(
        students=students,
        average=metrics.mean_of(averages),
        attendance_rate=metrics.mean_of(attendance_rates),
        homework_rate=metrics.mean_of(homework_rates),
        **risks,
        distribution=bands,
        attention=[summarize(s, m) for _, s, m in attention],
    )


@router.get("/calendar", response_model=schemas.CalendarOut)
def calendar(user: CurrentUser = Depends(current_user)):
    return {"timezone": school_timezone(), "today": school_today()}
