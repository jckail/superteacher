"""Real PostgreSQL acceptance checks; CI provides an isolated server."""

import os
import threading
import time
import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from superteacher.db import ROOT, run_migrations
from superteacher.models import OWNER_EMAIL, OWNER_ID


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


def _seed_owner(conn):
    # Empty-schema migrations create no accounts; course fixtures need a real
    # principal before exercising the independent grade constraints.
    conn.execute(
        text("INSERT INTO users (id, email, created_at, disabled) VALUES (:id, :email, CURRENT_TIMESTAMP, false)"),
        {"id": OWNER_ID, "email": OWNER_EMAIL},
    )


def _alembic_head() -> str:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert isinstance(head, str)
    return head


def test_postgres_concurrent_startup_migrations(postgres_engine, monkeypatch):
    """Five overlapping boots on one fresh schema must all reach a single head row.

    The pause is inside upgrade, after the migration transaction has started, so
    callers overlap in the DDL window unless a transaction advisory lock serializes them.
    """
    from alembic import command

    real_upgrade = command.upgrade

    def overlapping_upgrade(*args, **kwargs):
        time.sleep(0.3)
        real_upgrade(*args, **kwargs)

    monkeypatch.setattr(command, "upgrade", overlapping_upgrade)
    workers = 5
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def migrate() -> None:
        try:
            barrier.wait(timeout=30)
            run_migrations(postgres_engine)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=migrate) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert [thread.is_alive() for thread in threads] == [False] * workers
    assert errors == []
    with postgres_engine.connect() as conn:
        versions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    assert versions == [_alembic_head()]


def test_postgres_migration_persistence_and_grade_constraints(postgres_engine):
    engine = postgres_engine
    run_migrations(engine)
    with engine.begin() as conn:
        _seed_owner(conn)
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
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0004"
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE students SET grade_level = 13 WHERE id = 'p1'"))


def test_postgres_score_extra_credit_and_invalid_values(postgres_engine):
    engine = postgres_engine
    run_migrations(engine)
    with engine.begin() as conn:
        _seed_owner(conn)
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


@pytest.fixture
def export_roster_fixture(postgres_engine):
    """Cross batch boundaries with only synthetic owned and foreign rows."""
    from datetime import UTC, date, datetime, timedelta

    from sqlalchemy import insert
    from sqlalchemy.orm import sessionmaker

    from superteacher.models import (
        Assessment,
        AttendanceRecord,
        Course,
        InsightCache,
        Note,
        Score,
        Section,
        Student,
        User,
    )

    run_migrations(postgres_engine)
    stamp = datetime(2020, 2, 1, tzinfo=UTC)
    with postgres_engine.begin() as conn:
        _seed_owner(conn)
        conn.execute(insert(User), [{"id": "foreign", "email": "foreign@example.test", "created_at": stamp}])
        conn.execute(
            insert(Course),
            [
                {"id": "owned", "name": "Owned", "owner_id": OWNER_ID},
                {"id": "empty", "name": "Empty", "owner_id": OWNER_ID},
                {"id": "foreign", "name": "FOREIGN COURSE", "owner_id": "foreign"},
            ],
        )
        conn.execute(
            insert(Section),
            [
                {"id": "active", "course_id": "owned", "name": "Active"},
                {"id": "old", "course_id": "owned", "name": "Previous"},
                {"id": "empty", "course_id": "owned", "name": "Empty"},
                {"id": "foreign", "course_id": "foreign", "name": "FOREIGN SECTION"},
            ],
        )
        conn.execute(
            insert(Student),
            [
                {"id": f"s{i:06}", "name": f"Synthetic {i:06}", "grade_level": 9, "section_id": "active"}
                for i in range(205)
            ]
            + [{"id": "foreign", "name": "FOREIGN STUDENT", "grade_level": 9, "section_id": "foreign"}],
        )
        conn.execute(
            insert(Assessment),
            [
                {
                    "id": "active-test",
                    "section_id": "active",
                    "title": '=Test "quoted"',
                    "kind": "test",
                    "max_points": 100,
                    "due_date": date(2020, 1, 1),
                },
                {
                    "id": "active-hw",
                    "section_id": "active",
                    "title": "Homework",
                    "kind": "homework",
                    "max_points": 20,
                    "due_date": date(2020, 1, 2),
                },
                {
                    "id": "foreign",
                    "section_id": "foreign",
                    "title": "FOREIGN ASSESSMENT",
                    "kind": "test",
                    "max_points": 100,
                    "due_date": date(2020, 1, 1),
                },
            ]
            + [
                {
                    "id": f"old{i:06}",
                    "section_id": "old",
                    "title": f"Old {i:06}",
                    "kind": "quiz",
                    "max_points": 10,
                    "due_date": date(2019, 1, 1) + timedelta(days=i),
                }
                for i in range(121)
            ],
        )
        conn.execute(
            insert(Score),
            [
                {
                    "id": f"test{i:06}",
                    "student_id": f"s{i:06}",
                    "assessment_id": "active-test",
                    "points": None if i % 4 == 3 else [0, 68.123456789, 95][i % 4],
                }
                for i in range(205)
            ]
            + [
                {
                    "id": f"hw{i:06}",
                    "student_id": f"s{i:06}",
                    "assessment_id": "active-hw",
                    "points": 0 if i % 2 else None,
                }
                for i in range(205)
            ]
            + [
                {"id": f"hist{i:06}", "student_id": "s000000", "assessment_id": f"old{i:06}", "points": 10}
                for i in range(121)
            ]
            + [
                {"id": "crosscanary", "student_id": "s000000", "assessment_id": "foreign", "points": 99},
                {"id": "foreign", "student_id": "foreign", "assessment_id": "foreign", "points": 99},
            ],
        )
        conn.execute(
            insert(AttendanceRecord),
            [
                {"id": "owned-day", "student_id": "s000000", "day": date(2020, 1, 1), "status": "present"},
                {"id": "foreign-day", "student_id": "foreign", "day": date(2020, 1, 1), "status": "absent"},
            ],
        )
        conn.execute(
            insert(Note),
            [
                {"id": "owned-note", "student_id": "s000000", "body": "Owned note " + "é" * 70000, "created_at": stamp},
                {"id": "foreign-note", "student_id": "foreign", "body": "FOREIGN NOTE", "created_at": stamp},
            ],
        )
        conn.execute(
            insert(InsightCache),
            [
                {
                    "student_id": "s000000",
                    "fingerprint": "owned",
                    "model": "synthetic",
                    "payload": {"headline": "Owned insight"},
                    "created_at": stamp,
                },
                {
                    "student_id": "foreign",
                    "fingerprint": "foreign",
                    "model": "synthetic",
                    "payload": {"headline": "FOREIGN INSIGHT"},
                    "created_at": stamp,
                },
            ],
        )
    return sessionmaker(bind=postgres_engine, expire_on_commit=False), date(2020, 2, 1), stamp


def test_postgres_roster_pages_and_csv_column_batches(postgres_engine, export_roster_fixture):
    from itsdangerous import URLSafeSerializer
    from sqlalchemy import event

    from superteacher import gradebook_export, metrics, reports
    from superteacher.queries import load_students, owned_section, roster_page
    from superteacher.roster_pagination import PageQuery, decode_cursor, encode_cursor
    from superteacher.routers.roster import summarize

    factory, cutoff, _ = export_roster_fixture
    server_cursors = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if context.execution_options.get("yield_per"):
            server_cursors.append(getattr(cursor, "name", None))

    event.listen(postgres_engine, "after_cursor_execute", capture)
    try:
        with factory() as db:
            reference = [
                summarize(student, metrics.compute(student, cutoff))
                for student in load_students(db, OWNER_ID, section_id="active")
            ]
            # Independent stable reference, with null-last and raw name/id ties.
            ties = sorted(reference, key=lambda row: (row.name, row.id))
            expected = sorted([row for row in ties if row.average is not None], key=lambda row: row.average)
            expected += [row for row in ties if row.average is None]
            query = PageQuery(sort="average", limit=31)
            codec = URLSafeSerializer("synthetic-key", salt="superteacher-roster-page-v1")
            actual = []
            after = None
            while True:
                retained, matches, scoped = roster_page(db, OWNER_ID, query, cutoff, after)
                assert matches == scoped == 205
                assert len(retained) <= 32
                page = retained[:31]
                actual.extend(summarize(student, metric) for _, student, metric in page)
                if len(retained) <= 31:
                    break
                token = encode_cursor(codec, OWNER_ID, query, cutoff, page[-1][0])
                same_cutoff, after = decode_cursor(codec, token, OWNER_ID, query)
                assert same_cutoff == cutoff
            assert actual == expected
            assert len({row.id for row in actual}) == 205
            assert roster_page(db, OWNER_ID, PageQuery(course_id="foreign"), cutoff)[1:] == (0, 0)
            metadata = gradebook_export.read_metadata(db, OWNER_ID, "active")
            assert metadata is not None
            assert gradebook_export.read_metadata(db, OWNER_ID, "foreign") is None
            section = owned_section(db, OWNER_ID, "active")
            expected_csv = (
                "\ufeff" + reports.gradebook_csv(section, load_students(db, OWNER_ID, section_id="active"), cutoff)
            ).encode()
        chunks = list(gradebook_export.csv_chunks(factory, OWNER_ID, "active", metadata, cutoff))
        assert chunks and all(0 < len(chunk) <= gradebook_export.CHUNK_BYTES for chunk in chunks)
        assert b"".join(chunks) == expected_csv
        assert b"FOREIGN" not in b"".join(chunks)
        # psycopg named cursors establish execution of the real PG server-side path.
        assert server_cursors and all(server_cursors)
        assert postgres_engine.pool.checkedout() == 0
    finally:
        event.remove(postgres_engine, "after_cursor_execute", capture)


def test_postgres_class_summary_nested_cursors_and_native_parity(postgres_engine, export_roster_fixture):
    from sqlalchemy import event

    from superteacher import reports
    from superteacher.queries import load_students, owned_section
    from superteacher.report_summary import build_summary

    factory, cutoff, _ = export_roster_fixture
    with factory() as db:
        expected = reports.class_summary(
            owned_section(db, OWNER_ID, "active"), load_students(db, OWNER_ID, section_id="active"), cutoff
        ).model_dump(mode="json")
    cursors = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if context.execution_options.get("yield_per"):
            cursors.append(cursor)

    event.listen(postgres_engine, "after_cursor_execute", capture)
    try:
        with factory() as db:
            summary = build_summary(db, OWNER_ID, "active", cutoff)
            assert summary is not None
            actual = summary.model_dump(mode="json")
            assert actual == expected
            assert actual["students"] == 205
            assert "FOREIGN" not in summary.model_dump_json()
            assert len(db.identity_map) == 0
            assert build_summary(db, OWNER_ID, "foreign", cutoff) is None
            assert build_summary(db, OWNER_ID, "missing", cutoff) is None
        # More than 200 students forces child reads while the parent cursor is open.
        assert cursors and all(getattr(cursor, "name", None) for cursor in cursors)
        assert all(cursor.closed for cursor in cursors)
        assert postgres_engine.pool.checkedout() == 0
    finally:
        event.remove(postgres_engine, "after_cursor_execute", capture)


def test_postgres_account_nested_server_cursors_and_scope(postgres_engine, export_roster_fixture):
    import json

    from sqlalchemy import event

    from superteacher import account_export

    factory, _, stamp = export_roster_fixture
    server_cursors = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if context.execution_options.get("yield_per"):
            server_cursors.append(getattr(cursor, "name", None))

    event.listen(postgres_engine, "after_cursor_execute", capture)
    try:
        with factory() as db:
            metadata = account_export.read_metadata(db, OWNER_ID, OWNER_EMAIL, exported_at=stamp)
        # The nested column generators leave course/section/student cursors open while
        # consuming child cursors; >100 students and >100 histories cross fetch windows.
        chunks = list(account_export.account_chunks(factory, OWNER_ID, metadata))
        assert len(chunks) > 1
        assert all(0 < len(chunk) <= account_export.CHUNK_BYTES for chunk in chunks)
        raw = b"".join(chunks)
        assert b"FOREIGN" not in raw and b"crosscanary" not in raw
        document = json.loads(raw)
        assert document["account"]["email"] == OWNER_EMAIL
        assert document["exported_at"] == stamp.isoformat()
        courses = {course["id"]: course for course in document["courses"]}
        assert set(courses) == {"owned", "empty"}
        assert courses["empty"]["sections"] == []
        sections = {section["id"]: section for section in courses["owned"]["sections"]}
        assert set(sections) == {"active", "old", "empty"}
        assert sections["empty"]["students"] == sections["empty"]["assessments"] == []
        assert sections["old"]["students"] == []
        assert len(sections["old"]["assessments"]) == 121
        students = {student["id"]: student for student in sections["active"]["students"]}
        assert len(students) == 205
        first = students["s000000"]
        assert len(first["scores"]) == 123
        assert sum(score["section_id"] == "old" for score in first["scores"]) == 121
        assert {score["section_id"] for score in first["scores"]} == {"old", "active"}
        assert first["attendance"] == [{"day": "2020-01-01", "status": "present"}]
        assert first["notes"][0]["body"] == "Owned note " + "é" * 70000
        assert first["insight"]["payload"] == {"headline": "Owned insight"}
        assert students["s000001"]["notes"] == students["s000001"]["attendance"] == []
        assert students["s000001"]["insight"] is None
        assert server_cursors and all(server_cursors)
        assert postgres_engine.pool.checkedout() == 0
    finally:
        event.remove(postgres_engine, "after_cursor_execute", capture)
