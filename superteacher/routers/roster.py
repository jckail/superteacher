import csv
import io
import unicodedata

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import metrics, schemas
from ..accounts import CurrentUser
from ..auth import current_user
from ..calendar import school_today
from ..db import get_db
from ..models import Assessment, Course, Note, Score, Section, Student
from ..queries import (
    STUDENT_LOAD,
    iter_summaries,
    load_grade_history,
    owned_course,
    owned_section,
    owned_student,
    roster_page,
)
from ..roster_pagination import PageQuery, decode_cursor, encode_cursor

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


def get_student_or_404(db: Session, owner_id: str, student_id: str) -> Student:
    """404 for unknown ids AND for other users' students (indistinguishable)."""
    s = owned_student(db, owner_id, student_id, *STUDENT_LOAD, selectinload(Student.notes))
    if not s:
        raise HTTPException(404, "Student not found")
    return s


@router.get("/courses", response_model=list[schemas.CourseOut])
def list_courses(db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    q = select(Course).options(selectinload(Course.sections)).where(Course.owner_id == user.id).order_by(Course.name)
    return db.scalars(q).all()


def _name_taken(db: Session, model, name: str, **scope) -> bool:
    # Compare in Python: SQLite's lower() only folds ASCII, so "Ångström" / "ÅNGSTRÖM" would both be accepted.
    q = select(model.name)
    for k, v in scope.items():
        q = q.where(getattr(model, k) == v)
    wanted = name.casefold()
    return any(n.casefold() == wanted for n in db.scalars(q))


@router.post("/courses", response_model=schemas.CourseOut, status_code=201)
def create_course(body: schemas.CourseIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    if _name_taken(db, Course, body.name, owner_id=user.id):
        raise HTTPException(409, "A course with that name already exists")
    course = Course(name=body.name, owner_id=user.id)
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
def create_section(body: schemas.SectionIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    if not owned_course(db, user.id, body.course_id):
        raise HTTPException(404, "Course not found")
    if _name_taken(db, Section, body.name, course_id=body.course_id):
        raise HTTPException(409, "That section already exists in this course")
    section = Section(course_id=body.course_id, name=body.name)
    db.add(section)
    try:
        db.commit()
    except IntegrityError:
        # Exact matches and case variants both hit a unique index. A race that passed
        # _name_taken must be the same 409, not a 500.
        db.rollback()
        raise HTTPException(409, "That section already exists in this course") from None
    return section


@router.get("/students", response_model=list[schemas.StudentSummary])
def list_students(
    q: str | None = Query(default=None, max_length=120),
    course_id: str | None = None,
    section_id: str | None = None,
    risk: schemas.Risk | None = Query(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    rows = iter_summaries(db, user.id, retain_scores=False, q=q, course_id=course_id, section_id=section_id)
    return [summarize(s, m) for s, m in rows if not risk or m.risk == risk]


@router.get("/students/page", response_model=schemas.StudentPage)
def list_students_page(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Header(default=None, alias="X-Roster-Cursor"),
    q: str | None = Query(default=None, max_length=120),
    course_id: schemas.Id | None = None,
    section_id: schemas.Id | None = None,
    risk: schemas.Risk | None = None,
    sort: schemas.RosterSort = "risk",
    dir: schemas.RosterDirection = "asc",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    """Live fixed-calendar pages; Python lower search, raw name/id ties.

    Signed cursors contain readable names; keep out of shareable URLs and logs.
    """
    query = PageQuery(q or "", course_id, section_id, risk, sort, dir, limit)
    serializer = request.app.state.auth.roster_cursor_serializer()
    as_of, after = school_today(), None
    if cursor is not None:
        try:
            as_of, after = decode_cursor(serializer, cursor, user.id, query)
        except ValueError:
            raise HTTPException(400, "Invalid continuation") from None
    rows, matches, scoped = roster_page(db, user.id, query, as_of, after)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(serializer, user.id, query, as_of, rows[-1][0]) if has_more else None
    return schemas.StudentPage(
        items=[summarize(s, m) for _, s, m in rows],
        next_cursor=next_cursor,
        as_of=as_of,
        total_matches=matches,
        total_scoped=scoped,
    )


@router.post("/students", response_model=schemas.StudentDetail, status_code=201)
def create_student(body: schemas.StudentIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    if not owned_section(db, user.id, body.section_id):
        raise HTTPException(404, "Section not found")
    s = Student(name=body.name, grade_level=body.grade_level, section_id=body.section_id)
    db.add(s)
    sync_scores(db, s)
    db.commit()
    return detail(get_student_or_404(db, user.id, s.id))


@router.get("/students/{student_id}", response_model=schemas.StudentDetail)
def get_student(student_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    return detail(get_student_or_404(db, user.id, student_id))


@router.get("/students/{student_id}/grade-history", response_model=schemas.GradeHistory)
def get_grade_history(student_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    student = owned_student(db, user.id, student_id, selectinload(Student.section))
    if student is None:
        raise HTTPException(404, "Student not found")
    return schemas.GradeHistory(
        student_id=student.id,
        active_section_id=student.section_id,
        sections=load_grade_history(db, student.id, student.section_id, owner_id=user.id),
    )


@router.patch("/students/{student_id}", response_model=schemas.StudentDetail)
def update_student(
    student_id: str,
    body: schemas.StudentPatch,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    s = get_student_or_404(db, user.id, student_id)
    changes = body.model_dump(exclude_unset=True)
    if "section_id" in changes and not owned_section(db, user.id, changes["section_id"]):
        raise HTTPException(404, "Section not found")
    moved = "section_id" in changes and changes["section_id"] != s.section_id
    for k, v in changes.items():
        setattr(s, k, v)
    if moved:
        sync_scores(db, s)
    db.commit()
    db.expire_all()
    return detail(get_student_or_404(db, user.id, student_id))


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    db.delete(get_student_or_404(db, user.id, student_id))
    db.commit()
    return Response(status_code=204)


@router.post("/students/{student_id}/notes", response_model=schemas.NoteOut, status_code=201)
def add_note(
    student_id: str, body: schemas.NoteIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)
):
    s = get_student_or_404(db, user.id, student_id)
    note = Note(student_id=s.id, body=body.body)
    db.add(note)
    db.commit()
    return note


def _student_note_or_404(db: Session, owner_id: str, student_id: str, note_id: str) -> Note:
    if owned_student(db, owner_id, student_id, selectinload(Student.section)) is None:
        raise HTTPException(404, "Note not found")
    note = db.scalar(select(Note).where(Note.id == note_id, Note.student_id == student_id))
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.patch("/students/{student_id}/notes/{note_id}", response_model=schemas.NoteOut)
def update_note(
    student_id: str,
    note_id: str,
    body: schemas.NoteIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    note = _student_note_or_404(db, user.id, student_id, note_id)
    note.body = body.body
    db.commit()
    return note


@router.delete("/students/{student_id}/notes/{note_id}", status_code=204)
def delete_note(
    student_id: str, note_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)
):
    db.delete(_student_note_or_404(db, user.id, student_id, note_id))
    db.commit()
    return Response(status_code=204)


@router.post("/sections/{section_id}/import", response_model=schemas.ImportResult)
def import_students(
    section_id: str,
    body: schemas.ImportIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    """Bulk-add students from CSV (``name,grade_level``, header optional). Bad rows are skipped, not fatal."""
    if not owned_section(db, user.id, section_id):
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
        if (
            i == 1
            and name.lower() in {"name", "student", "student name"}
            and len(row) > 1
            and " ".join(row[1].split()).lower() in {"grade_level", "grade level", "grade"}
        ):
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
