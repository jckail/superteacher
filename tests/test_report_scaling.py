"""Report lookup cost and ordering retain calendar, transfer and missing-grade contracts."""

from datetime import UTC, date, datetime, timedelta
from statistics import mean
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from superteacher import calendar, reports
from superteacher.db import Base
from superteacher.models import AssessmentKind, AttendanceRecord, AttendanceStatus, Course, Section, Student
from superteacher.queries import load_students

DAY = date(2026, 3, 1)


class CountedScores(list):
    iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def assessment(aid, *, section_id="active", due=DAY, max_points=100):
    return SimpleNamespace(
        id=aid, section_id=section_id, title=aid, kind=AssessmentKind.quiz, due_date=due, max_points=max_points
    )


def score(a, points):
    return SimpleNamespace(assessment_id=a.id, assessment=a, points=points)


def student(sid, scores, attendance=()):
    return SimpleNamespace(
        id=sid, name=sid, section_id="active", scores=CountedScores(scores), attendance=list(attendance), notes=[]
    )


def section(assessments):
    return SimpleNamespace(id="active", name="P1", course=SimpleNamespace(name="Synthetic"), assessments=assessments)


@pytest.mark.parametrize("n_assessments", [20, 60])
def test_thousand_student_report_score_lookup_is_linear(n_assessments):
    assignments = [assessment(f"a{i}", max_points=50 if i % 2 else 100) for i in range(n_assessments)]
    students = [
        student(
            f"s{j}",
            [
                score(a, None if (i + j) % 7 == 0 else a.max_points * ((i + j) % 51 + 50) / 100)
                for i, a in enumerate(assignments)
            ],
        )
        for j in range(1000)
    ]
    result = reports.class_summary(section(assignments), students, DAY)
    assert sum(s.scores.iterations for s in students) == 2 * len(students)
    for stat in result.assessments:
        a = next(a for a in assignments if a.id == stat.id)
        values = [sc.points for s in students for sc in s.scores if sc.assessment_id == a.id]
        percentages = [v / a.max_points * 100 for v in values if v is not None]
        assert stat.graded == len(percentages)
        assert stat.average == round(mean(percentages), 1)
        assert stat.missing_pct == round((len(students) - len(percentages)) / len(students) * 100, 1)


def test_report_calendar_cutoff_missing_and_preserved_transfer_grades(monkeypatch):
    # UTC is already tomorrow, while the school is still on DAY.
    monkeypatch.setattr(calendar, "utc_now", lambda: datetime(2026, 3, 2, 0, 30, tzinfo=UTC))
    due = assessment("due", max_points=50)
    missing = assessment("missing")
    absent_row = assessment("absent-row")
    future = assessment("future", due=DAY + timedelta(days=1))
    historical = assessment("old", section_id="previous")
    s = student(
        "s",
        [score(due, 40), score(missing, None), score(future, None), score(historical, 0)],
        [
            SimpleNamespace(day=DAY, status=AttendanceStatus.present),
            SimpleNamespace(day=DAY + timedelta(days=1), status=AttendanceStatus.absent),
        ],
    )
    with calendar.school_calendar("America/Los_Angeles"):
        result = reports.class_summary(section([due, missing, absent_row, future]), [s])
    assert result.as_of == DAY and result.average == 80
    assert result.attendance_rate == 100 and [a.day for a in result.attendance] == [DAY]
    stats = {a.id: a for a in result.assessments}
    assert set(stats) == {"due", "missing", "absent-row", "future"}
    assert stats["due"].average == 80 and stats["due"].missing_pct == 0
    assert stats["missing"].missing_pct == stats["absent-row"].missing_pct == 100
    assert stats["future"].missing_pct is None
    assert result.distribution == {"A": 0, "B": 1, "C": 0, "D": 0, "F": 0}


def test_bulk_attendance_is_student_then_day_and_each_student_is_chronological(engine):
    Base.metadata.create_all(engine)
    days = [DAY, DAY - timedelta(days=2), DAY - timedelta(days=1)]
    with Session(engine) as db:
        sec = Section(id="active", name="P1", course=Course(id="c", name="Synthetic"))
        students = [Student(id=sid, name=sid, grade_level=9, section=sec) for sid in ("a", "b")]
        db.add_all(students)
        db.flush()
        db.add_all(
            AttendanceRecord(student=s, day=day, status=AttendanceStatus.present)
            for day in days
            for s in reversed(students)
        )
        db.commit()
    statements = []

    def capture(conn, cursor, sql, params, context, many):
        if "FROM attendance" in sql:
            statements.append(sql)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            students = load_students(db, section_id="active")
            assert [s.id for s in students] == ["a", "b"]
            for s in students:
                assert [r.day for r in s.attendance] == sorted(days)
                assert all(r.student_id == s.id for r in s.attendance)
        with Session(engine) as db:
            assert [r.day for r in load_students(db, student_id="b")[0].attendance] == sorted(days)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert statements and all("ORDER BY attendance.student_id, attendance.day" in sql for sql in statements)
