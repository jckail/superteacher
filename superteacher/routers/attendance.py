from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import AttendanceRecord, Section, Student

router = APIRouter(tags=["attendance"])


def _sheet(db: Session, section: Section, day: date) -> schemas.AttendanceSheet:
    students = db.scalars(select(Student).where(Student.section_id == section.id).order_by(Student.name)).all()
    marks = {
        r.student_id: r.status
        for r in db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.day == day, AttendanceRecord.student_id.in_([s.id for s in students])
            )
        )
    }
    return schemas.AttendanceSheet(
        section=schemas.SectionOut.model_validate(section),
        day=day,
        rows=[schemas.AttendanceSheetRow(student_id=s.id, name=s.name, status=marks.get(s.id)) for s in students],
    )


@router.get("/sections/{section_id}/attendance", response_model=schemas.AttendanceSheet)
def get_sheet(section_id: str, day: date | None = None, db: Session = Depends(get_db)):
    section = db.get(Section, section_id)
    if not section:
        raise HTTPException(404, "Section not found")
    return _sheet(db, section, day or date.today())


@router.put("/sections/{section_id}/attendance", response_model=schemas.AttendanceSheet)
def put_sheet(section_id: str, body: schemas.AttendanceIn, db: Session = Depends(get_db)):
    section = db.get(Section, section_id)
    if not section:
        raise HTTPException(404, "Section not found")
    enrolled = set(db.scalars(select(Student.id).where(Student.section_id == section_id)))
    existing = {
        r.student_id: r
        for r in db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.day == body.day, AttendanceRecord.student_id.in_(enrolled))
        )
    }
    latest = {m.student_id: m for m in body.marks}  # repeated student in one request: last mark wins
    for sid in latest:
        if sid not in enrolled:
            raise HTTPException(422, f"Student {sid} is not in this section")
    for sid, mark in latest.items():
        if rec := existing.get(sid):
            rec.status = mark.status
        else:
            db.add(AttendanceRecord(student_id=sid, day=body.day, status=mark.status))
    db.commit()
    return _sheet(db, section, body.day)
