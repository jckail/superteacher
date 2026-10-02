"""Storage enforces the same numeric and enum domains as API validation."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from superteacher.db import Base, make_engine


@pytest.fixture
def engine():
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO courses VALUES ('c', 'Math')"))
        conn.execute(text("INSERT INTO sections VALUES ('sec', 'c', 'A')"))
        conn.execute(text("INSERT INTO students VALUES ('s', 'Student', 8, 'sec')"))
        conn.execute(text("INSERT INTO assessments VALUES ('a', 'sec', 'Test', 'test', 100, '2026-10-01')"))
    yield eng
    eng.dispose()


@pytest.mark.parametrize(
    ("table", "column", "invalid"),
    [
        ("students", "grade_level", 0),
        ("students", "grade_level", 13),
        ("students", "grade_level", 1.5),
        ("assessments", "max_points", 0),
        ("assessments", "max_points", -1),
        ("assessments", "max_points", 1_000_001),
        ("assessments", "max_points", float("inf")),
        ("assessments", "max_points", float("nan")),
        ("assessments", "kind", "exam"),
    ],
)
def test_invalid_direct_updates_are_rejected(engine, table, column, invalid):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET {column} = :value"), {"value": invalid})


@pytest.mark.parametrize("points", [-1, float("inf"), float("-inf")])
def test_invalid_direct_score_inserts_are_rejected(engine, points):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO scores VALUES ('score', 'a', 's', :points)"), {"points": points})


def test_invalid_direct_attendance_insert_is_rejected(engine):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO attendance VALUES ('att', 's', '2026-10-01', 'unknown')"))


@pytest.mark.parametrize("points", [None, 0, 125, 1.7976931348623157e308])
def test_missing_zero_extra_credit_and_finite_maximum_scores_are_allowed(engine, points):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO scores VALUES ('score', 'a', 's', :points)"), {"points": points})
    with engine.connect() as conn:
        assert conn.execute(text("SELECT points FROM scores")).scalar() == points


@pytest.mark.parametrize("grade", [1, 12])
@pytest.mark.parametrize("maximum", [0.001, 1_000_000])
def test_numeric_boundaries_are_allowed(engine, grade, maximum):
    with engine.begin() as conn:
        conn.execute(text("UPDATE students SET grade_level = :grade"), {"grade": grade})
        conn.execute(text("UPDATE assessments SET max_points = :maximum"), {"maximum": maximum})
