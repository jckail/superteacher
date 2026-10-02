"""Read-side database queries shared by routers and services (AI chat, reports).

Lives below both layers: it depends only on ``models`` and ``metrics``, so a service never has to import a router.
"""

from collections.abc import Iterator
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from . import metrics
from .calendar import school_today
from .models import OWNER_ID, Assessment, AttendanceRecord, Course, Score, Section, Student

# Notes are only needed on the detail page (and for one focused student in the AI context), so they
# stay lazy for roster-wide loads and are eager only in get_student_or_404.
STUDENT_LOAD = (
    selectinload(Student.scores).selectinload(Score.assessment),
    selectinload(Student.attendance),
    joinedload(Student.section).joinedload(Section.course),
)


# ── tenancy ─────────────────────────────────────────────────────────────
# Every read of course-owned data goes through ``owner_id``. The owned_* helpers return None for ids that do not
# exist OR belong to someone else, so callers cannot tell the difference (routers turn None into 404).
def owned_course(db: Session, owner_id: str, course_id: str) -> Course | None:
    return db.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))


def owned_section(db: Session, owner_id: str, section_id: str, *options) -> Section | None:
    q = select(Section).join(Course).where(Section.id == section_id, Course.owner_id == owner_id)
    return db.scalar(q.options(*options))


def owned_assessment(db: Session, owner_id: str, assessment_id: str, *options) -> Assessment | None:
    q = select(Assessment).join(Section).join(Course).where(Assessment.id == assessment_id, Course.owner_id == owner_id)
    return db.scalar(q.options(*options))


def owned_student(db: Session, owner_id: str, student_id: str, *options) -> Student | None:
    q = select(Student).join(Section).join(Course).where(Student.id == student_id, Course.owner_id == owner_id)
    return db.scalar(q.options(*(options or STUDENT_LOAD)))


def _scoped(q, owner_id: str):
    """Restrict a Student query (already joined to Section) to one owner's courses."""
    return q.join(Course, Course.id == Section.course_id).where(Course.owner_id == owner_id)


def _literal_pattern(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _text_match(column, value: str, filters: dict):
    lower = func.st_python_lower if filters.get("_python_lower") else func.lower
    return lower(column).like(_literal_pattern(value.lower()), escape="\\")


def _tool_filters(db: Session, filters: dict) -> dict:
    # SQLite lower() only handles ASCII. Tool matching historically uses Python Unicode lower().
    if (filters.get("section") or filters.get("name_contains")) and db.bind.dialect.name == "sqlite":
        db.connection().connection.driver_connection.create_function(
            "st_python_lower", 1, lambda text: text.lower() if text is not None else None, deterministic=True
        )
        return {**filters, "_python_lower": True}
    return filters


def _filtered(q, filters: dict):
    if filters.get("course_id"):
        q = q.where(Section.course_id == filters["course_id"])
    if filters.get("section_id"):
        q = q.where(Student.section_id == filters["section_id"])
    if filters.get("student_id"):
        q = q.where(Student.id == filters["student_id"])
    if filters.get("section"):
        q = q.where(
            or_(
                _text_match(Section.name, filters["section"], filters),
                Section.course.has(_text_match(Course.name, filters["section"], filters)),
            )
        )
    if filters.get("name_contains"):
        q = q.where(_text_match(Student.name, filters["name_contains"], filters))
    if filters.get("q"):
        # Escape LIKE wildcards so "%" / "_" in a search are literal characters.
        q = q.where(Student.name.ilike(_literal_pattern(filters["q"]), escape="\\"))
    return q


def load_students(db: Session, owner_id: str = OWNER_ID, **filters) -> list[Student]:
    filters = _tool_filters(db, filters)
    q = _filtered(
        _scoped(select(Student).options(*STUDENT_LOAD).join(Section), owner_id).order_by(Student.name, Student.id),
        filters,
    )
    return list(db.scalars(q).unique())


def student_candidates(db: Session, owner_id: str = OWNER_ID, *, limit: int = 10, **filters) -> list[Student]:
    """Metadata only; lookup ambiguity never hydrates unrelated student history."""
    filters = _tool_filters(db, filters)
    q = _filtered(
        _scoped(select(Student).options(joinedload(Student.section).joinedload(Section.course)).join(Section), owner_id)
        .order_by(Student.name, Student.id)
        .limit(limit),
        filters,
    )
    return list(db.scalars(q).unique())


def summaries_for(
    db: Session,
    students: list[Student],
    *,
    owner_id: str = OWNER_ID,
    retain_scores: bool = True,
    today: date | None = None,
):
    """Read history only for this bounded batch, using column rows instead of ORM objects."""
    if not students:
        return
    students = [s for s in students if s.section.course.owner_id == owner_id]
    if not students:
        return
    today = today or school_today()
    ids = [s.id for s in students]
    points: dict[str, list[metrics.ScorePoint]] = {}
    for sid, aid, title, kind, due, mx, pts in db.execute(
        select(
            Score.student_id,
            Assessment.id,
            Assessment.title,
            Assessment.kind,
            Assessment.due_date,
            Assessment.max_points,
            Score.points,
        )
        .join(Assessment, Assessment.id == Score.assessment_id)
        .join(Student, Student.id == Score.student_id)
        .where(Score.student_id.in_(ids), Assessment.section_id == Student.section_id)
        .execution_options(yield_per=1000)
    ):
        points.setdefault(sid, []).append(metrics.make_point(aid, title, kind, due, mx, pts))
    statuses: dict[str, list] = {}
    for sid, status in db.execute(
        select(AttendanceRecord.student_id, AttendanceRecord.status)
        .where(AttendanceRecord.student_id.in_(ids), AttendanceRecord.day <= today)
        .execution_options(yield_per=1000)
    ):
        statuses.setdefault(sid, []).append(status)
    for s in students:
        m = metrics.compute_from(points.pop(s.id, []), statuses.pop(s.id, []), today)
        if not retain_scores:
            m.scores = []
        yield s, m


def iter_summaries(
    db: Session,
    owner_id: str = OWNER_ID,
    *,
    batch_size: int = 200,
    retain_scores: bool = True,
    today: date | None = None,
    **filters,
) -> Iterator:
    """Stream roster metadata and history in bounded batches, preserving name/id order."""
    today = today or school_today()
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    filters = _tool_filters(db, filters)
    q = _filtered(
        _scoped(select(Student).options(joinedload(Student.section).joinedload(Section.course)).join(Section), owner_id)
        .order_by(Student.name, Student.id)
        .execution_options(yield_per=batch_size),
        filters,
    )
    for students in db.scalars(q).partitions(batch_size):
        yield from summaries_for(db, students, retain_scores=retain_scores, today=today, owner_id=owner_id)


def load_summaries(db: Session, owner_id: str = OWNER_ID, **filters) -> list[tuple[Student, metrics.StudentMetrics]]:
    """Students plus metrics for list/overview/gradebook views, without ORM history hydration."""
    return list(iter_summaries(db, owner_id, **filters))


def load_grade_history(db: Session, student_id: str, active_section_id: str, *, owner_id: str = OWNER_ID) -> list[dict]:
    """Prior-section raw grades only, read as student-scoped columns without ORM history hydration."""
    authorized_ids = _scoped(select(Student.id).join(Section), owner_id).where(Student.id == student_id).correlate(None)
    sections = {}
    rows = db.execute(
        select(
            Section.id,
            Section.name,
            Course.id,
            Course.name,
            Assessment.id,
            Assessment.title,
            Assessment.kind,
            Assessment.due_date,
            Assessment.max_points,
            Score.points,
        )
        .select_from(Score)
        .join(Assessment, Assessment.id == Score.assessment_id)
        .join(Section, Section.id == Assessment.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(
            Score.student_id.in_(authorized_ids),
            Assessment.section_id != active_section_id,
            Course.owner_id == owner_id,
        )
        .order_by(Course.name, Section.name, Section.id, Assessment.due_date, Assessment.title, Assessment.id)
        .execution_options(yield_per=1000)
    )
    for sid, section, cid, course, aid, title, kind, due, maximum, points in rows:
        if sid not in sections:
            sections[sid] = {"section_id": sid, "section": section, "course_id": cid, "course": course, "scores": []}
        point = metrics.make_point(aid, title, kind, due, maximum, points)
        sections[sid]["scores"].append(vars(point))
    return list(sections.values())
