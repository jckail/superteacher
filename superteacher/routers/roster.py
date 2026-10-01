import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import metrics, schemas
from ..db import get_db
from ..models import Course, Note, Score, Section, Student

router = APIRouter(tags=["roster"])

_student_load = (
    selectinload(Student.scores).selectinload(Score.assessment),
    selectinload(Student.attendance),
    selectinload(Student.notes),
    selectinload(Student.section).selectinload(Section.course),
)


def summarize(s: Student, m: metrics.StudentMetrics | None = None) -> schemas.StudentSummary:
    m = m or metrics.compute(s)
    return schemas.StudentSummary(
        id=s.id, name=s.name, grade_level=s.grade_level,
        section_id=s.section_id, section=s.section.name,
        course_id=s.section.course_id, course=s.section.course.name,
        average=m.average, letter=m.letter, gpa=m.gpa, trend=m.trend,
        attendance_rate=m.attendance_rate, homework_rate=m.homework_rate,
        missing=m.missing, risk=m.risk, risk_reasons=m.risk_reasons,
    )  # fmt: skip


def detail(s: Student) -> schemas.StudentDetail:
    m = metrics.compute(s)
    return schemas.StudentDetail(
        **summarize(s, m).model_dump(),
        scores=[schemas.ScoreOut(**vars(p)) for p in m.scores],
        attendance=[schemas.AttendanceOut.model_validate(a) for a in s.attendance],
        absences=m.absences, tardies=m.tardies,
        notes=[schemas.NoteOut.model_validate(n) for n in s.notes],
    )  # fmt: skip


def load_students(db: Session, **filters) -> list[Student]:
    q = select(Student).options(*_student_load).join(Section).order_by(Student.name)
    if filters.get("course_id"):
        q = q.where(Section.course_id == filters["course_id"])
    if filters.get("section_id"):
        q = q.where(Student.section_id == filters["section_id"])
    if filters.get("q"):
        q = q.where(Student.name.ilike(f"%{filters['q']}%"))
    return list(db.scalars(q).unique())


def get_student_or_404(db: Session, student_id: str) -> Student:
    s = db.scalar(select(Student).options(*_student_load).where(Student.id == student_id))
    if not s:
        raise HTTPException(404, "Student not found")
    return s


@router.get("/courses", response_model=list[schemas.CourseOut])
def list_courses(db: Session = Depends(get_db)):
    return db.scalars(select(Course).options(selectinload(Course.sections)).order_by(Course.name)).all()


@router.post("/courses", response_model=schemas.CourseOut, status_code=201)
def create_course(body: schemas.CourseIn, db: Session = Depends(get_db)):
    course = Course(name=body.name.strip())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A course with that name already exists") from None
    return course


@router.post("/sections", response_model=schemas.SectionOut, status_code=201)
def create_section(body: schemas.SectionIn, db: Session = Depends(get_db)):
    if not db.get(Course, body.course_id):
        raise HTTPException(404, "Course not found")
    section = Section(course_id=body.course_id, name=body.name.strip())
    db.add(section)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That section already exists in this course") from None
    return section


@router.get("/students", response_model=list[schemas.StudentSummary])
def list_students(
    q: str | None = None,
    course_id: str | None = None,
    section_id: str | None = None,
    risk: str | None = Query(default=None, pattern="^(on_track|watch|at_risk)$"),
    db: Session = Depends(get_db),
):
    rows = [summarize(s) for s in load_students(db, q=q, course_id=course_id, section_id=section_id)]
    return [r for r in rows if not risk or r.risk == risk]


@router.post("/students", response_model=schemas.StudentDetail, status_code=201)
def create_student(body: schemas.StudentIn, db: Session = Depends(get_db)):
    if not db.get(Section, body.section_id):
        raise HTTPException(404, "Section not found")
    s = Student(name=body.name.strip(), grade_level=body.grade_level, section_id=body.section_id)
    db.add(s)
    db.commit()
    return detail(get_student_or_404(db, s.id))


@router.get("/students/{student_id}", response_model=schemas.StudentDetail)
def get_student(student_id: str, db: Session = Depends(get_db)):
    return detail(get_student_or_404(db, student_id))


@router.patch("/students/{student_id}", response_model=schemas.StudentDetail)
def update_student(student_id: str, body: schemas.StudentPatch, db: Session = Depends(get_db)):
    s = get_student_or_404(db, student_id)
    changes = body.model_dump(exclude_unset=True)
    if "section_id" in changes and not db.get(Section, changes["section_id"]):
        raise HTTPException(404, "Section not found")
    for k, v in changes.items():
        setattr(s, k, v)
    db.commit()
    db.expire_all()
    return detail(get_student_or_404(db, student_id))


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: str, db: Session = Depends(get_db)):
    db.delete(get_student_or_404(db, student_id))
    db.commit()
    return Response(status_code=204)


@router.post("/students/{student_id}/notes", response_model=schemas.NoteOut, status_code=201)
def add_note(student_id: str, body: schemas.NoteIn, db: Session = Depends(get_db)):
    s = get_student_or_404(db, student_id)
    note = Note(student_id=s.id, body=body.body.strip())
    db.add(note)
    db.commit()
    return note


@router.post("/sections/{section_id}/import", response_model=schemas.ImportResult)
def import_students(section_id: str, body: schemas.ImportIn, db: Session = Depends(get_db)):
    """Bulk-add students from CSV with columns ``name,grade_level`` (header optional). Bad rows are skipped, not fatal."""
    if not db.get(Section, section_id):
        raise HTTPException(404, "Section not found")
    existing = {n.lower() for n in db.scalars(select(Student.name).where(Student.section_id == section_id))}
    created, skipped = 0, []
    for i, row in enumerate(csv.reader(io.StringIO(body.csv.lstrip("\ufeff"))), start=1):
        if not row or not "".join(row).strip():
            continue
        name = row[0].strip()
        if i == 1 and name.lower() in {"name", "student", "student name"}:
            continue
        try:
            level = int(row[1]) if len(row) > 1 and row[1].strip() else 9
            if not 1 <= level <= 12 or not 0 < len(name) <= 120:
                raise ValueError
        except ValueError:
            skipped.append(f"Row {i}: invalid name or grade level")
            continue
        if name.lower() in existing:
            skipped.append(f"Row {i}: {name} is already in this section")
            continue
        existing.add(name.lower())
        db.add(Student(name=name, grade_level=level, section_id=section_id))
        created += 1
    db.commit()
    return schemas.ImportResult(created=created, skipped=skipped)
