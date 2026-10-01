from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import metrics, schemas
from ..db import get_db
from ..models import Assessment, Score, Section, Student
from .roster import load_students

router = APIRouter(tags=["gradebook"])


def _section(db: Session, section_id: str) -> Section:
    s = db.get(Section, section_id)
    if not s:
        raise HTTPException(404, "Section not found")
    return s


def build_gradebook(db: Session, section: Section) -> schemas.Gradebook:
    assessments = db.scalars(
        select(Assessment).where(Assessment.section_id == section.id).order_by(Assessment.due_date, Assessment.title)
    ).all()
    rows = []
    for st in load_students(db, section_id=section.id):
        m = metrics.compute(st)
        rows.append(
            schemas.GradebookRow(
                student_id=st.id, name=st.name, average=m.average, letter=m.letter,
                points={sp.assessment_id: sp.points for sp in m.scores},
            )  # fmt: skip
        )
    return schemas.Gradebook(
        section=schemas.SectionOut.model_validate(section),
        assessments=[schemas.AssessmentOut.model_validate(a) for a in assessments],
        rows=rows,
    )


@router.get("/sections/{section_id}/gradebook", response_model=schemas.Gradebook)
def gradebook(section_id: str, db: Session = Depends(get_db)):
    return build_gradebook(db, _section(db, section_id))


@router.post("/sections/{section_id}/assessments", response_model=schemas.Gradebook, status_code=201)
def create_assessment(section_id: str, body: schemas.AssessmentIn, db: Session = Depends(get_db)):
    section = _section(db, section_id)
    a = Assessment(section_id=section.id, **body.model_dump())
    db.add(a)
    db.flush()
    # Every enrolled student gets an empty score row so "missing" is explicit, not implied.
    for st in db.scalars(select(Student).where(Student.section_id == section.id)):
        db.add(Score(assessment_id=a.id, student_id=st.id, points=None))
    db.commit()
    return build_gradebook(db, section)


@router.put("/assessments/{assessment_id}/scores", response_model=schemas.Gradebook)
def put_scores(assessment_id: str, body: schemas.ScoresIn, db: Session = Depends(get_db)):
    a = db.scalar(select(Assessment).options(selectinload(Assessment.scores)).where(Assessment.id == assessment_id))
    if not a:
        raise HTTPException(404, "Assessment not found")
    by_student = {sc.student_id: sc for sc in a.scores}
    enrolled = set(db.scalars(select(Student.id).where(Student.section_id == a.section_id)))
    for entry in body.scores:
        if entry.student_id not in enrolled:
            raise HTTPException(422, f"Student {entry.student_id} is not in this section")
        if entry.points is not None and entry.points > a.max_points * 1.5:
            raise HTTPException(422, f"{entry.points} is far above the {a.max_points:g}-point maximum")
        sc = by_student.get(entry.student_id)
        if sc:
            sc.points = entry.points
        else:
            db.add(Score(assessment_id=a.id, student_id=entry.student_id, points=entry.points))
    db.commit()
    return build_gradebook(db, _section(db, a.section_id))


@router.delete("/assessments/{assessment_id}", response_model=schemas.Gradebook)
def delete_assessment(assessment_id: str, db: Session = Depends(get_db)):
    a = db.get(Assessment, assessment_id)
    if not a:
        raise HTTPException(404, "Assessment not found")
    section = _section(db, a.section_id)
    db.delete(a)
    db.commit()
    return build_gradebook(db, section)
