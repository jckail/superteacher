"""Overview parity and retained candidates; synthetic data only."""

import weakref
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import insert
from sqlalchemy.orm import Session

from superteacher import metrics, queries, schemas
from superteacher.accounts import CurrentUser
from superteacher.models import Assessment, AttendanceRecord, Course, Score, Section, Student, User
from superteacher.routers import system
from superteacher.routers.roster import summarize
from tests import test_query_scale

TODAY = date(2026, 10, 1)
USER = CurrentUser("owner", "synthetic@example.invalid")


@pytest.fixture(autouse=True)
def fixed_cutoff(monkeypatch):
    monkeypatch.setattr(system, "school_today", lambda: TODAY)


def student(i):
    return SimpleNamespace(
        id=str(i),
        name=f"Student {i}",
        grade_level=9,
        section_id="s",
        section=SimpleNamespace(name="Section", course_id="c", course=SimpleNamespace(name="Course")),
    )


def reference(rows):
    rows = list(rows)
    flagged = sorted(
        (pair for pair in rows if pair[1].risk in ("at_risk", "watch")),
        key=lambda pair: (
            {"at_risk": 0, "watch": 1}[pair[1].risk],
            pair[1].average if pair[1].average is not None else 101,
        ),
    )
    return schemas.Overview(
        as_of=TODAY,
        students=len(rows),
        average=metrics.mean_of(m.average for _, m in rows),
        attendance_rate=metrics.mean_of(m.attendance_rate for _, m in rows),
        homework_rate=metrics.mean_of(m.homework_rate for _, m in rows),
        **{risk: sum(m.risk == risk for _, m in rows) for risk in ("at_risk", "watch", "on_track", "unknown")},
        distribution={band: sum(bool(m.letter) and m.letter[0] == band for _, m in rows) for band in "ABCDF"},
        attention=[summarize(s, m) for s, m in flagged[:8]],
    )


def test_attention_retention_does_not_materialize_all_metrics(monkeypatch):
    refs = []
    peak = 0
    closed = []

    def stream(*args, **kwargs):
        nonlocal peak
        assert kwargs == {"retain_scores": False, "today": TODAY, "course_id": "c", "section_id": "s"}
        try:
            for i in range(600):
                metric = metrics.StudentMetrics(average=float(600 - i), risk="at_risk")
                refs.append(weakref.ref(metric))
                peak = max(peak, sum(ref() is not None for ref in refs))
                yield student(i), metric
        finally:
            closed.append(True)

    monkeypatch.setattr(system, "iter_summaries", stream)
    result = system.overview(course_id="c", section_id="s", db=None, user=USER)
    assert peak <= 10  # <=8 winners plus generator/current iteration temporaries
    assert closed == [True]
    assert result.students == result.at_risk == 600
    assert [s.id for s in result.attention] == [str(i) for i in range(599, 591, -1)]


def test_stable_sentinel_and_exact_means(monkeypatch):
    values = [None, 101.0, 101.00000001, 1e308, 1e308, 0.0, 70.123456789, 70.123456789, None, 0.0, 101.0, 20.0]
    rows = [
        (
            student(i),
            metrics.StudentMetrics(
                average=value,
                risk="watch" if i >= 9 else "at_risk",
                letter=metrics.letter_and_gpa(value)[0],
                attendance_rate=None if i % 3 == 0 else i / 3,
                homework_rate=0.0 if i % 2 else None,
            ),
        )
        for i, value in enumerate(values)
    ]
    monkeypatch.setattr(system, "iter_summaries", lambda *args, **kwargs: (row for row in rows))
    actual = system.overview(db=None, user=USER)
    assert actual.model_dump() == reference(rows).model_dump()
    assert [s.id for s in actual.attention][:7] == ["5", "6", "7", "0", "1", "8", "2"]


@pytest.mark.parametrize("failure", ["iteration", "reducer"])
def test_iterator_closed_on_failure(monkeypatch, failure):
    closed = []

    def stream(*args, **kwargs):
        try:
            yield student(0), metrics.StudentMetrics(risk="at_risk", average="bad" if failure == "reducer" else 50)
            if failure == "iteration":
                raise RuntimeError("synthetic iteration failure")
            yield student(1), metrics.StudentMetrics(risk="at_risk", average=40)
        finally:
            closed.append(True)

    monkeypatch.setattr(system, "iter_summaries", stream)
    with pytest.raises((RuntimeError, TypeError)):
        system.overview(db=None, user=USER)
    assert closed == [True]


@pytest.fixture
def native_world(engine, monkeypatch):
    monkeypatch.setattr(test_query_scale, "school_today", lambda: TODAY)
    monkeypatch.setattr(queries, "school_today", lambda: TODAY)
    test_query_scale.seed_scale(engine, students=205, assignments=6, days=5)
    with engine.begin() as conn:
        owner = conn.execute(Course.__table__.select()).first().owner_id
        conn.execute(insert(User), {"id": "foreign", "email": "foreign@example.invalid"})
        conn.execute(insert(Course), {"id": "foreign-c", "name": "Foreign", "owner_id": "foreign"})
        conn.execute(insert(Course), {"id": "own-other", "name": "Other owned", "owner_id": owner})
        conn.execute(
            insert(Section),
            [
                {"id": "foreign-s", "name": "Foreign", "course_id": "foreign-c"},
                {"id": "empty", "name": "Empty", "course_id": "course"},
            ],
        )
        conn.execute(
            insert(Student), {"id": "foreign-st", "name": "Foreign", "grade_level": 9, "section_id": "foreign-s"}
        )
        conn.execute(
            insert(Assessment),
            {
                "id": "old",
                "section_id": "sec1",
                "title": "Retained history",
                "kind": "test",
                "max_points": 100,
                "due_date": TODAY,
            },
        )
        conn.execute(insert(Score), {"id": "old-score", "student_id": "s000000", "assessment_id": "old", "points": 0})
        # Special owned students: unknown, attendance-only, due NULL homework,
        # future zero and fractional extra credit. Ordinary scale rows cross batches.
        conn.execute(
            insert(Student),
            [
                {"id": f"edge{i}", "name": name, "grade_level": 9, "section_id": "sec0"}
                for i, name in enumerate(["Ada", "Ada", "ada", "Éva", "Ω"])
            ],
        )
        conn.execute(
            insert(Assessment),
            [
                {
                    "id": "edge-hw",
                    "section_id": "sec0",
                    "title": "Null homework",
                    "kind": "homework",
                    "max_points": 10,
                    "due_date": TODAY,
                },
                {
                    "id": "edge-future",
                    "section_id": "sec0",
                    "title": "Future",
                    "kind": "quiz",
                    "max_points": 10,
                    "due_date": TODAY + timedelta(days=1),
                },
                {
                    "id": "edge-grade",
                    "section_id": "sec0",
                    "title": "Extra",
                    "kind": "test",
                    "max_points": 10,
                    "due_date": TODAY,
                },
            ],
        )
        conn.execute(
            insert(Score),
            [
                {"id": "edge-null", "student_id": "edge2", "assessment_id": "edge-hw", "points": None},
                {"id": "edge-zero", "student_id": "edge3", "assessment_id": "edge-future", "points": 0},
                {"id": "edge-extra", "student_id": "edge4", "assessment_id": "edge-grade", "points": 20.123456789},
            ],
        )
        conn.execute(
            insert(AttendanceRecord),
            [
                {"id": "edge-absent", "student_id": "edge1", "day": TODAY, "status": "absent"},
                {"id": "edge-excused", "student_id": "edge0", "day": TODAY, "status": "excused"},
                {"id": "edge-future-att", "student_id": "edge0", "day": TODAY + timedelta(days=1), "status": "absent"},
            ],
        )
    return owner


@pytest.mark.parametrize(
    "course,section",
    [
        (None, None),
        ("course", None),
        (None, "sec0"),
        ("course", "sec1"),
        ("foreign-c", None),
        (None, "foreign-s"),
        ("missing", None),
        (None, "missing"),
        ("course", "foreign-s"),
        ("own-other", "sec0"),
        (None, "empty"),
    ],
)
def test_native_complete_response_parity(engine, native_world, course, section):
    filters = {"course_id": course, "section_id": section}
    with Session(engine) as db:
        expected = reference((s, metrics.compute(s, TODAY)) for s in queries.load_students(db, native_world, **filters))
    with Session(engine) as db:
        actual = system.overview(db=db, user=CurrentUser(native_world, "own@example.invalid"), **filters)
        assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
        assert not any(isinstance(obj, (Score, Assessment, AttendanceRecord)) for obj in db.identity_map.values())
