"""Read-side database queries shared by routers and services (AI chat, reports).

Lives below both layers: it depends only on ``models`` and ``metrics``, so a service never has to import a router.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from . import metrics
from .models import Assessment, AttendanceRecord, Score, Section, Student

# Notes are only needed on the detail page (and for one focused student in the AI context), so they
# stay lazy for roster-wide loads and are eager only in get_student_or_404.
STUDENT_LOAD = (
    selectinload(Student.scores).selectinload(Score.assessment),
    selectinload(Student.attendance),
    joinedload(Student.section).joinedload(Section.course),
)


def _filtered(q, filters: dict):
    if filters.get("course_id"):
        q = q.where(Section.course_id == filters["course_id"])
    if filters.get("section_id"):
        q = q.where(Student.section_id == filters["section_id"])
    if filters.get("q"):
        # Escape LIKE wildcards so "%" / "_" in a search are literal characters.
        needle = filters["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.where(Student.name.ilike(f"%{needle}%", escape="\\"))
    return q


def load_students(db: Session, **filters) -> list[Student]:
    q = _filtered(select(Student).options(*STUDENT_LOAD).join(Section).order_by(Student.name, Student.id), filters)
    return list(db.scalars(q).unique())


def load_summaries(db: Session, **filters) -> list[tuple[Student, metrics.StudentMetrics]]:
    """Students plus metrics for list/overview/gradebook views.

    Scores and attendance are read as plain column tuples (two queries) instead of hydrating
    tens of thousands of ORM objects; the numbers come from the same ``metrics`` code.
    """
    q = _filtered(
        select(Student).options(joinedload(Student.section).joinedload(Section.course)).join(Section)
        .order_by(Student.name, Student.id),
        filters,
    )  # fmt: skip
    students = list(db.scalars(q).unique())
    if not students:
        return []
    ids_q = _filtered(select(Student.id).join(Section), filters).scalar_subquery()
    points: dict[str, list[metrics.ScorePoint]] = {}
    for sid, aid, title, kind, due, mx, pts in db.execute(
        select(Score.student_id, Assessment.id, Assessment.title, Assessment.kind, Assessment.due_date,
               Assessment.max_points, Score.points)
        .join(Assessment, Assessment.id == Score.assessment_id)
        .where(Score.student_id.in_(ids_q))
    ):  # fmt: skip
        points.setdefault(sid, []).append(metrics.make_point(aid, title, kind, due, mx, pts))
    statuses: dict[str, list] = {}
    for sid, status in db.execute(
        select(AttendanceRecord.student_id, AttendanceRecord.status).where(AttendanceRecord.student_id.in_(ids_q))
    ):
        statuses.setdefault(sid, []).append(status)
    return [(s, metrics.compute_from(points.get(s.id, []), statuses.get(s.id, []))) for s in students]
