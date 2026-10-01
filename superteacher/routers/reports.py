from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from .. import reports as svc
from ..db import get_db
from ..models import Section
from .roster import get_student_or_404, load_students

router = APIRouter(tags=["reports"])


class ParentUpdateIn(BaseModel):
    tone: svc.Tone = "warm"


class ParentUpdateOut(BaseModel):
    subject: str
    body: str
    source: str  # "ai" | "template"


def _section_or_404(db: Session, section_id: str) -> Section:
    sec = db.get(Section, section_id, options=[selectinload(Section.assessments), selectinload(Section.course)])
    if not sec:
        raise HTTPException(404, "Section not found")
    return sec


@router.get("/reports/sections/{section_id}/gradebook.csv")
def gradebook_csv(section_id: str, db: Session = Depends(get_db)):
    sec = _section_or_404(db, section_id)
    body = svc.gradebook_csv(sec, load_students(db, section_id=section_id))
    name = f"gradebook-{svc.slug(sec.course.name)}-{svc.slug(sec.name)}.csv"
    return Response(
        "﻿" + body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.get("/reports/sections/{section_id}/summary", response_model=svc.ClassSummary)
def class_summary(section_id: str, db: Session = Depends(get_db)):
    sec = _section_or_404(db, section_id)
    return svc.class_summary(sec, load_students(db, section_id=section_id))


@router.post("/reports/students/{student_id}/parent-update", response_model=ParentUpdateOut)
async def parent_update(student_id: str, body: ParentUpdateIn, db: Session = Depends(get_db)):
    student = get_student_or_404(db, student_id)
    draft, source = await svc.parent_update(student, body.tone)
    return ParentUpdateOut(subject=draft.subject, body=draft.body, source=source)
