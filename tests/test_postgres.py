"""Real PostgreSQL acceptance checks; CI provides an isolated server."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from superteacher.db import run_migrations
from superteacher.models import OWNER_ID


@pytest.fixture
def postgres_engine():
    url = os.environ.get("ST_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("ST_TEST_POSTGRES_URL is required for PostgreSQL integration")
    schema = "st_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}))
    try:
        yield scoped
    finally:
        scoped.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_migration_persistence_and_grade_constraints(postgres_engine):
    engine = postgres_engine
    run_migrations(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO courses (id, name, owner_id) VALUES ('c1', 'Synthetic Math', :owner)"),
            {"owner": OWNER_ID},
        )
        conn.execute(text("INSERT INTO sections (id, course_id, name) VALUES ('s1', 'c1', 'Period 1')"))
        conn.execute(
            text("INSERT INTO students (id, name, grade_level, section_id) VALUES ('p1', 'Synthetic', 9, 's1')")
        )
    engine.dispose()
    run_migrations(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM students WHERE id = 'p1'")).scalar_one() == "Synthetic"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003"
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE students SET grade_level = 13 WHERE id = 'p1'"))


def test_postgres_score_extra_credit_and_invalid_values(postgres_engine):
    engine = postgres_engine
    run_migrations(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO courses (id, name, owner_id) VALUES ('c1', 'Math', :owner)"), {"owner": OWNER_ID}
        )
        conn.execute(text("INSERT INTO sections (id, course_id, name) VALUES ('s1', 'c1', 'Period 1')"))
        conn.execute(
            text("INSERT INTO students (id, name, grade_level, section_id) VALUES ('p1', 'Synthetic', 9, 's1')")
        )
        conn.execute(
            text(
                "INSERT INTO assessments (id, section_id, title, kind, max_points, due_date) "
                "VALUES ('a1', 's1', 'Quiz', 'quiz', 100, '2026-10-01')"
            )
        )
        conn.execute(text("INSERT INTO scores (id, assessment_id, student_id, points) VALUES ('v1', 'a1', 'p1', 120)"))
    for value in [-1, float("inf"), float("nan")]:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text("UPDATE scores SET points = :value WHERE id = 'v1'"), {"value": value})
    with engine.connect() as conn:
        assert conn.execute(text("SELECT points FROM scores WHERE id = 'v1'")).scalar_one() == 120
