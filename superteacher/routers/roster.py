import csv
import io
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import metrics, schemas
from ..calendar import school_today
from ..db import get_db
from ..models import Assessment, Course, Note, Score, Section, Student
from ..queries import STUDENT_LOAD, iter_summaries, load_grade_history

router = APIRouter(tags=["roster"])

MAX_IMPORT_ROWS = 5000


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
    as_of = school_today()
    m = metrics.compute(s, as_of)
    return schemas.StudentDetail(
        **summarize(s, m).model_dump(),
        as_of=as_of,
        scores=[schemas.ScoreOut(**vars(p)) for p in m.scores],
        attendance=[schemas.AttendanceOut.model_validate(a) for a in s.attendance],
        absences=m.absences, tardies=m.tardies,
        notes=[schemas.NoteOut.model_validate(n) for n in s.notes],
    )  # fmt: skip


def sync_scores(db: Session, student: Student) -> None:
    """Add missing active-section score rows while preserving all previously recorded history."""
    db.flush()
    have = set(db.scalars(select(Score.assessment_id).where(Score.student_id == student.id)))
    for aid in db.scalars(select(Assessment.id).where(Assessment.section_id == student.section_id)):
        if aid not in have:
            db.add(Score(assessment_id=aid, student_id=student.id, points=None))
    db.flush()
    db.expire(student, ["scores"])


def get_student_or_404(db: Session, student_id: str) -> Student:
    s = db.scalar(select(Student).options(*STUDENT_LOAD, selectinload(Student.notes)).where(Student.id == student_id))
    if not s:
        raise HTTPException(404, "Student not found")
    return s


@router.get("/courses", response_model=list[schemas.CourseOut])
def list_courses(db: Session = Depends(get_db)):
    return db.scalars(select(Course).options(selectinload(Course.sections)).order_by(Course.name)).all()


def _name_taken(db: Session, model, name: str, **scope) -> bool:
    # Compare in Python: SQLite's lower() only folds ASCII, so "Ångström" / "ÅNGSTRÖM" would both be accepted.
    q = select(model.name)
    for k, v in scope.items():
        q = q.where(getattr(model, k) == v)
    wanted = name.casefold()
    return any(n.casefold() == wanted for n in db.scalars(q))


@router.post("/courses", response_model=schemas.CourseOut, status_code=201)
def create_course(body: schemas.CourseIn, db: Session = Depends(get_db)):
    if _name_taken(db, Course, body.name):
        raise HTTPException(409, "A course with that name already exists")
    course = Course(name=body.name)
    if body.initial_section_name is not None:
        course.sections.append(Section(name=body.initial_section_name))
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if body.initial_section_name is not None:
            raise HTTPException(
                409, "The course and initial section could not be created. No changes were saved."
            ) from None
        raise HTTPException(409, "A course with that name already exists") from None
    return course


@router.post("/sections", response_model=schemas.SectionOut, status_code=201)
def create_section(body: schemas.SectionIn, db: Session = Depends(get_db)):
    if not db.get(Course, body.course_id):
        raise HTTPException(404, "Course not found")
    if _name_taken(db, Section, body.name, course_id=body.course_id):
        raise HTTPException(409, "That section already exists in this course")
    section = Section(course_id=body.course_id, name=body.name)
    db.add(section)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That section already exists in this course") from None
    return section


@router.get("/students", response_model=list[schemas.StudentSummary])
def list_students(
    q: str | None = Query(default=None, max_length=120),
    course_id: str | None = None,
    section_id: str | None = None,
    risk: str | None = Query(default=None, pattern="^(on_track|watch|at_risk)$"),
    db: Session = Depends(get_db),
):
    rows = iter_summaries(db, retain_scores=False, q=q, course_id=course_id, section_id=section_id)
    return [summarize(s, m) for s, m in rows if not risk or m.risk == risk]


@router.post("/students", response_model=schemas.StudentDetail, status_code=201)
def create_student(body: schemas.StudentIn, db: Session = Depends(get_db)):
    if not db.get(Section, body.section_id):
        raise HTTPException(404, "Section not found")
    s = Student(name=body.name, grade_level=body.grade_level, section_id=body.section_id)
    db.add(s)
    sync_scores(db, s)
    db.commit()
    return detail(get_student_or_404(db, s.id))


@router.get("/students/{student_id}", response_model=schemas.StudentDetail)
def get_student(student_id: str, db: Session = Depends(get_db)):
    return detail(get_student_or_404(db, student_id))


@router.get("/students/{student_id}/grade-history", response_model=schemas.GradeHistory)
def get_grade_history(student_id: str, db: Session = Depends(get_db)):
    student = db.execute(select(Student.id, Student.section_id).where(Student.id == student_id)).first()
    if student is None:
        raise HTTPException(404, "Student not found")
    return schemas.GradeHistory(
        student_id=student.id,
        active_section_id=student.section_id,
        sections=load_grade_history(db, student.id, student.section_id),
    )


@router.patch("/students/{student_id}", response_model=schemas.StudentDetail)
def update_student(student_id: str, body: schemas.StudentPatch, db: Session = Depends(get_db)):
    s = get_student_or_404(db, student_id)
    changes = body.model_dump(exclude_unset=True)
    if "section_id" in changes and not db.get(Section, changes["section_id"]):
        raise HTTPException(404, "Section not found")
    moved = "section_id" in changes and changes["section_id"] != s.section_id
    for k, v in changes.items():
        setattr(s, k, v)
    if moved:
        sync_scores(db, s)
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
    note = Note(student_id=s.id, body=body.body)
    db.add(note)
    db.commit()
    return note


def _student_note_or_404(db: Session, student_id: str, note_id: str) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.student_id == student_id))
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.patch("/students/{student_id}/notes/{note_id}", response_model=schemas.NoteOut)
def update_note(student_id: str, note_id: str, body: schemas.NoteIn, db: Session = Depends(get_db)):
    note = _student_note_or_404(db, student_id, note_id)
    note.body = body.body
    db.commit()
    return note


@router.delete("/students/{student_id}/notes/{note_id}", status_code=204)
def delete_note(student_id: str, note_id: str, db: Session = Depends(get_db)):
    db.delete(_student_note_or_404(db, student_id, note_id))
    db.commit()
    return Response(status_code=204)


@router.post("/sections/{section_id}/import", response_model=schemas.ImportResult)
def import_students(section_id: str, body: schemas.ImportIn, db: Session = Depends(get_db)):
    """Bulk-add students from CSV (``name,grade_level``, header optional). Bad rows are skipped, not fatal."""
    if not db.get(Section, section_id):
        raise HTTPException(404, "Section not found")
    existing = {
        unicodedata.normalize("NFC", n).casefold()
        for n in db.scalars(select(Student.name).where(Student.section_id == section_id))
    }
    created, skipped, new = 0, [], []
    try:
        rows = list(csv.reader(io.StringIO(body.csv.lstrip("\ufeff").replace("\x00", ""))))
    except csv.Error as e:
        raise HTTPException(422, f"Could not parse CSV: {e}") from None
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(422, f"Too many rows (max {MAX_IMPORT_ROWS})")
    for i, row in enumerate(rows, start=1):
        if not row or not "".join(row).strip():
            continue
        name = unicodedata.normalize("NFC", " ".join(row[0].split()))
        if i == 1 and name.lower() in {"name", "student", "student name"}:
            continue
        try:
            level = int(row[1]) if len(row) > 1 and row[1].strip() else 9
            if (
                not 1 <= level <= 12
                or not 0 < len(name) <= 120
                or any(unicodedata.category(c) in ("Cc", "Cs") for c in name)
            ):
                raise ValueError
        except ValueError:
            skipped.append(f"Row {i}: invalid name or grade level")
            continue
        if name.casefold() in existing:
            skipped.append(f"Row {i}: {name} is already in this section")
            continue
        existing.add(name.casefold())
        st = Student(name=name, grade_level=level, section_id=section_id)
        db.add(st)
        new.append(st)
        created += 1
    db.flush()
    if new:
        for aid in db.scalars(select(Assessment.id).where(Assessment.section_id == section_id)).all():
            db.add_all(Score(assessment_id=aid, student_id=st.id, points=None) for st in new)
    db.commit()
    return schemas.ImportResult(created=created, skipped=skipped)
