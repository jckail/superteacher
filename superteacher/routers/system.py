from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import metrics, schemas
from ..accounts import CurrentUser
from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..queries import load_summaries
from .roster import summarize

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "ok", "ai": bool(get_settings().anthropic_api_key)}
    except Exception:
        return {"status": "unhealthy", "database": "error", "ai": False}


@router.get("/version")
def version():
    return {"version": get_settings().version}


@router.get("/overview", response_model=schemas.Overview)
def overview(
    course_id: str | None = None,
    section_id: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    computed = load_summaries(db, user.id, course_id=course_id, section_id=section_id)

    bands = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for _, m in computed:
        if m.letter:
            bands[m.letter[0]] += 1
    order = {"at_risk": 0, "watch": 1, "on_track": 2}
    flagged = sorted(
        (c for c in computed if c[1].risk != "on_track"),
        key=lambda c: (order[c[1].risk], c[1].average if c[1].average is not None else 101),
    )
    return schemas.Overview(
        students=len(computed),
        average=metrics.mean_of(m.average for _, m in computed),
        attendance_rate=metrics.mean_of(m.attendance_rate for _, m in computed),
        homework_rate=metrics.mean_of(m.homework_rate for _, m in computed),
        at_risk=sum(1 for _, m in computed if m.risk == "at_risk"),
        watch=sum(1 for _, m in computed if m.risk == "watch"),
        distribution=bands,
        attention=[summarize(s, m) for s, m in flagged[:8]],
    )
