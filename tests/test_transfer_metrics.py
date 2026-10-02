"""Active metrics ignore preserved grades; history reads have a strict student boundary."""

from dataclasses import asdict

from sqlalchemy import event
from sqlalchemy.orm import Session

from superteacher import metrics
from superteacher.calendar import school_today
from superteacher.db import Base
from superteacher.models import Assessment, AssessmentKind, Course, Score, Section, Student
from superteacher.queries import load_grade_history, load_students, load_summaries


def test_unflushed_metrics_keep_none_section_semantics():
    assessment = Assessment(id="a", title="Quiz", kind=AssessmentKind.quiz, due_date=school_today(), max_points=100)
    student = Student(name="Unflushed", grade_level=9)
    student.scores.append(Score(assessment=assessment, points=80))
    assert student.section_id is None and assessment.section_id is None
    assert metrics.compute(student).average == 80


def test_column_and_orm_metrics_use_only_active_section(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        course = Course(id="c", name="Synthetic")
        old = Section(id="old", name="Old", course=course)
        active = Section(id="active", name="Active", course=course)
        s = Student(id="s", name="Student", grade_level=9, section=active)
        other = Student(id="other", name="Other student", grade_level=9, section=active)
        assessments = [
            Assessment(
                id=f"a{i}",
                title=f"Quiz {i}",
                section=sec,
                kind=AssessmentKind.quiz,
                max_points=100,
                due_date=school_today(),
            )
            for i, sec in enumerate([old, old, active, active])
        ]
        db.add_all([s, other, *assessments])
        db.flush()
        db.add_all(
            [
                Score(student=s, assessment=a, points=pts)
                for a, pts in zip(assessments, [0, None, 90, None], strict=True)
            ]
        )
        db.add(Score(student=other, assessment=assessments[0], points=40))
        db.commit()
    statements = []

    def capture(conn, cursor, sql, params, context, many):
        statements.append((sql, params))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            s = load_students(db, student_id="s")[0]
            orm = metrics.compute(s)
            columns = load_summaries(db, student_id="s")[0][1]
            assert asdict(columns) == asdict(orm)
            assert orm.average == 90 and orm.missing == 1
            assert {p.assessment_id for p in orm.scores} == {"a2", "a3"}
        statements.clear()
        with Session(engine) as db:
            history = load_grade_history(db, "s", "active")
            assert len(statements) == 1 and statements[0][1] == ("s", "active")
            assert not db.identity_map
            assert len(history) == 1 and history[0]["section_id"] == "old"
            assert {p["assessment_id"]: p["points"] for p in history[0]["scores"]} == {"a0": 0, "a1": None}
            assert history[0]["scores"][0]["pct"] == 0
            assert "Other student" not in str(history)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
