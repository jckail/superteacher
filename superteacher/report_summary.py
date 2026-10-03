"""Column-only class summary with native metrics and exact assessment medians.

Retains one metric batch, one assessment's percentages, scalar mean inputs and
required flagged output. These scale with active assessment count, roster size
and a student's lifetime attendance; this is not a global memory/CPU bound.
Reads are live across statements, not a snapshot or disconnect-interruptible work.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import metrics, reports
from .calendar import school_today
from .gradebook_export import read_metadata
from .models import Assessment, AttendanceRecord, AttendanceStatus, Course, Score, Section, Student

STUDENT_BATCH = 200
FETCH_ROWS = 1000


def _score_query(owner_id, section_id, *columns):
    # The same expected section on both ends binds the assessment's owner to
    # the joined current student/course owner, even for malformed score links.
    return (
        select(*columns)
        .select_from(Score)
        .join(Student, Student.id == Score.student_id)
        .join(Section, Section.id == Student.section_id)
        .join(Course, Course.id == Section.course_id)
        .join(Assessment, Assessment.id == Score.assessment_id)
        .where(Course.owner_id == owner_id, Student.section_id == section_id, Assessment.section_id == section_id)
    )


def _attendance_query(owner_id, section_id, *columns):
    return (
        select(*columns)
        .select_from(AttendanceRecord)
        .join(Student, Student.id == AttendanceRecord.student_id)
        .join(Section, Section.id == Student.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Course.owner_id == owner_id, Student.section_id == section_id)
    )


def _rows(db, query) -> Iterator:
    result = db.execute(query.execution_options(yield_per=FETCH_ROWS))
    try:
        for batch in result.partitions(FETCH_ROWS):
            yield from batch
    finally:
        result.close()


def _metric_batch(db, owner_id, section_id, students, today):
    ids = [student.id for student in students]
    points, statuses = {}, {}
    rows = _rows(
        db,
        _score_query(
            owner_id,
            section_id,
            Score.student_id,
            Assessment.id,
            Assessment.title,
            Assessment.kind,
            Assessment.due_date,
            Assessment.max_points,
            Score.points,
        ).where(Student.id.in_(ids)),
    )
    try:
        for sid, aid, title, kind, due, maximum, value in rows:
            points.setdefault(sid, []).append(metrics.make_point(aid, title, kind, due, maximum, value))
    finally:
        rows.close()
    rows = _rows(
        db,
        _attendance_query(owner_id, section_id, AttendanceRecord.student_id, AttendanceRecord.status).where(
            Student.id.in_(ids), AttendanceRecord.day <= today
        ),
    )
    try:
        for sid, status in rows:
            statuses.setdefault(sid, []).append(status)
    finally:
        rows.close()
    for student in students:
        yield student, metrics.compute_from(points.pop(student.id, []), statuses.pop(student.id, []), today)


def _stat(assessment, percentages, submitted, student_count, today):
    return reports.AssessmentStat(
        id=assessment.id,
        title=assessment.title,
        kind=assessment.kind,
        due_date=assessment.due_date,
        max_points=assessment.max_points,
        graded=len(percentages),
        average=reports._pct(mean(percentages)) if percentages else None,
        median=reports._pct(reports._finite_median(percentages)) if percentages else None,
        min=reports._pct(min(percentages)) if percentages else None,
        max=reports._pct(max(percentages)) if percentages else None,
        missing_pct=reports._pct((student_count - submitted) / student_count * 100)
        if assessment.due_date <= today and student_count
        else None,
    )


def _assessment_stats(db, owner_id, section_id, assessments, student_count, today):
    by_id = {assessment.id: assessment for assessment in assessments}
    completed = {}
    current, percentages, submitted = None, [], 0
    rows = _rows(db, _score_query(owner_id, section_id, Assessment.id, Score.points).order_by(Score.assessment_id))
    try:
        for aid, value in rows:
            if aid not in by_id:
                continue  # newly-created metadata is outside this response's preflight
            if aid != current:
                if current is not None:
                    completed[current] = _stat(by_id[current], percentages, submitted, student_count, today)
                current, percentages, submitted = aid, [], 0
            if value is not None:
                submitted += 1
                if by_id[aid].max_points:
                    percentages.append(value / by_id[aid].max_points * 100)
        if current is not None:
            completed[current] = _stat(by_id[current], percentages, submitted, student_count, today)
    finally:
        rows.close()
    # Stable metadata order mirrors the pure helper; internal grouping adds no
    # public ID tie policy. Assessments without score rows still appear.
    return [completed[a.id] if a.id in completed else _stat(a, [], 0, student_count, today) for a in assessments]


def _attendance_strip(db, owner_id, section_id, today):
    counters = {}
    rows = _rows(
        db,
        _attendance_query(owner_id, section_id, AttendanceRecord.day, AttendanceRecord.status).where(
            AttendanceRecord.day >= today - timedelta(days=29), AttendanceRecord.day <= today
        ),
    )
    try:
        for day, status in rows:
            marked, counted, attended, absent = counters.get(day, (0, 0, 0, 0))
            counters[day] = (
                marked + 1,
                counted + (status is not AttendanceStatus.excused),
                attended + (status in (AttendanceStatus.present, AttendanceStatus.tardy)),
                absent + (status is AttendanceStatus.absent),
            )
    finally:
        rows.close()
    return [
        reports.AttendanceDay(
            day=day, marked=marked, rate=reports._pct(attended / counted * 100) if counted else None, absent=absent
        )
        for day, (marked, counted, attended, absent) in sorted(counters.items())
    ]


def build_summary(
    db: Session, owner_id: str, section_id: str, today: date | None = None
) -> reports.ClassSummary | None:
    """Caller owns the request session; each result/child iterator closes explicitly."""
    today = today or school_today()
    metadata = read_metadata(db, owner_id, section_id)
    if metadata is None:
        return None
    query = (
        select(Student.id, Student.name)
        .join(Section)
        .join(Course)
        .where(Course.owner_id == owner_id, Student.section_id == section_id)
        .order_by(Student.name, Student.id)
        .execution_options(yield_per=STUDENT_BATCH)
    )
    student_count, averages, rates, attention = 0, [], [], []
    risks = dict.fromkeys(("unknown", "on_track", "watch", "at_risk"), 0)
    bands = dict.fromkeys(("A", "B", "C", "D", "F"), 0)
    result = db.execute(query)
    try:
        for students in result.partitions(STUDENT_BATCH):
            batch = _metric_batch(db, owner_id, section_id, students, today)
            try:
                for student, computed in batch:
                    student_count += 1
                    risks[computed.risk] += 1
                    if computed.letter:
                        bands[computed.letter[0]] += 1
                    if computed.average is not None:
                        averages.append(computed.average)
                    if computed.attendance_rate is not None:
                        rates.append(computed.attendance_rate)
                    if computed.risk in ("at_risk", "watch"):
                        attention.append(
                            (
                                (
                                    0 if computed.risk == "at_risk" else 1,
                                    computed.average if computed.average is not None else 101,
                                ),
                                reports.AttentionItem(
                                    id=student.id,
                                    name=student.name,
                                    risk=computed.risk,
                                    average=reports._pct(computed.average),
                                    reasons=computed.risk_reasons,
                                ),
                            )
                        )
            finally:
                batch.close()
    finally:
        result.close()
    attention.sort(key=lambda item: item[0])  # stable: raw SQL name/id ties
    return reports.ClassSummary(
        as_of=today,
        section_id=section_id,
        section=metadata.section,
        course=metadata.course,
        students=student_count,
        **risks,
        distribution=bands,
        average=reports._pct(mean(averages)) if averages else None,
        attendance_rate=reports._pct(mean(rates)) if rates else None,
        attention=[item for _, item in attention],
        assessments=_assessment_stats(db, owner_id, section_id, metadata.assessments, student_count, today),
        attendance=_attendance_strip(db, owner_id, section_id, today),
    )
