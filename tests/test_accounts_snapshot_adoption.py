"""Offline accounts adoption preserves owners/history and never changes its input."""

import os
import sqlite3
import stat
from contextlib import closing

import pytest
from sqlalchemy import create_engine, inspect

from superteacher import adopt_accounts_snapshot as adoption
from superteacher import db as database


@pytest.fixture
def published_snapshot(tmp_path):
    source = tmp_path / "published-accounts.db"
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as connection:
        adoption._apply(connection, database.ROOT / "alembic/versions/0001_initial_schema.py")
        adoption._apply(connection, database.ROOT / "superteacher/legacy_accounts_0002.py")
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('0002')")
        connection.exec_driver_sql("INSERT INTO users VALUES ('u', 'teacher@example.com', '2026-10-01', NULL, 0)")
        connection.exec_driver_sql("INSERT INTO courses VALUES ('c', 'Math', 'u')")
        connection.exec_driver_sql("INSERT INTO sections VALUES ('old', 'c', 'Old'), ('new', 'c', 'New')")
        connection.exec_driver_sql("INSERT INTO students VALUES ('s', 'Synthetic', 8, 'new')")
        connection.exec_driver_sql("INSERT INTO assessments VALUES ('a', 'old', 'Prior', 'quiz', 10, '2026-09-01')")
        connection.exec_driver_sql("INSERT INTO scores VALUES ('score', 'a', 's', 12)")
        connection.exec_driver_sql("INSERT INTO attendance VALUES ('att', 's', '2026-10-01', 'present')")
        connection.exec_driver_sql("INSERT INTO notes VALUES ('n', 's', 'Synthetic note', '2026-10-01')")
        connection.exec_driver_sql("INSERT INTO insights VALUES ('s', 'fp', 'rules', '{}', '2026-10-01')")
        connection.exec_driver_sql(
            "INSERT INTO sessions VALUES ('hash', 'u', '2026-10-01', '2026-11-01', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login_tokens VALUES "
            "('tokenhash', 'teacher@example.com', '2026-10-01', '2026-11-01', NULL, NULL)"
        )
        connection.exec_driver_sql("INSERT INTO usage_counters VALUES ('u', '2026-10-01', 'chat', 3)")
        connection.exec_driver_sql("INSERT INTO ai_budget VALUES ('2026-10-01', 3)")
    engine.dispose()
    source.chmod(0o400)
    return source


def rows(path):
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        return {
            name: connection.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version' ORDER BY name"
            ).fetchall()
        }


def mutate(source, statement):
    source.chmod(0o600)
    with closing(sqlite3.connect(source)) as connection:
        connection.execute(statement)
        connection.commit()
    source.chmod(0o400)


def test_published_accounts_snapshot_adopts_on_a_clone_without_record_changes(published_snapshot, tmp_path):
    source = published_snapshot
    original_bytes, original_rows = source.read_bytes(), rows(source)
    destination = tmp_path / "adopted.db"
    adoption.adopt_accounts_snapshot(source, destination)
    assert source.read_bytes() == original_bytes
    assert rows(destination) == original_rows
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    engine = create_engine(f"sqlite:///{destination}")
    try:
        assert {c["name"] for c in inspect(engine).get_check_constraints("scores")} == {"ck_scores_points"}
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0003"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        database.run_migrations(engine)  # Native startup accepts the explicitly adopted output.
        assert rows(destination) == original_rows
    finally:
        engine.dispose()
    assert not list(tmp_path.glob(".superteacher-adopt-*"))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE alembic_version SET version_num='0001'",
        "ALTER TABLE students ADD COLUMN unexpected TEXT",
        "DROP INDEX uq_courses_owner_name",
        "CREATE TABLE unrelated (value TEXT)",
        "UPDATE scores SET points=-1",
        "UPDATE students SET grade_level=13",
        "UPDATE scores SET student_id='missing'",
    ],
)
def test_unproven_or_invalid_snapshot_produces_no_output(published_snapshot, tmp_path, statement):
    source = published_snapshot
    mutate(source, statement)
    before = source.read_bytes()
    destination = tmp_path / "rejected.db"
    with pytest.raises((adoption.AdoptionError, adoption.BackupError)):
        adoption.adopt_accounts_snapshot(source, destination)
    assert not destination.exists()
    assert source.read_bytes() == before
    assert not list(tmp_path.glob(".superteacher-adopt-*"))


def test_writable_or_active_source_is_rejected(published_snapshot, tmp_path):
    source = published_snapshot
    source.chmod(0o600)
    with pytest.raises(adoption.AdoptionError, match="read-only offline snapshot"):
        adoption.adopt_accounts_snapshot(source, tmp_path / "output.db")
    source.chmod(0o400)
    sidecar = tmp_path / (source.name + "-wal")
    sidecar.write_bytes(b"synthetic active marker")
    with pytest.raises(adoption.AdoptionError, match="sidecars"):
        adoption.adopt_accounts_snapshot(source, tmp_path / "output.db")


def test_existing_destination_or_source_alias_is_never_overwritten(published_snapshot, tmp_path):
    destination = tmp_path / "existing.db"
    destination.write_bytes(b"keep")
    with pytest.raises(adoption.AdoptionError, match="new file"):
        adoption.adopt_accounts_snapshot(published_snapshot, destination)
    assert destination.read_bytes() == b"keep"
    alias = tmp_path / "alias.db"
    os.link(published_snapshot, alias)
    with pytest.raises(adoption.AdoptionError, match="new file"):
        adoption.adopt_accounts_snapshot(published_snapshot, alias)


def test_destination_created_during_publication_is_preserved(published_snapshot, tmp_path, monkeypatch):
    destination = tmp_path / "competing.db"
    original_link = os.link

    def competing_link(source, target):
        if target == destination:
            destination.write_bytes(b"competing writer")
        return original_link(source, target)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(adoption.BackupError, match="already exists"):
        adoption.adopt_accounts_snapshot(published_snapshot, destination)
    assert destination.read_bytes() == b"competing writer"
    assert not list(tmp_path.glob(".superteacher-adopt-*"))
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_native_schema_drift_prevents_adoption(published_snapshot, tmp_path, monkeypatch):
    original_apply = adoption._apply

    def changed_native_migration(connection, path):
        original_apply(connection, path)
        if path.name == "0003_accounts.py":
            connection.exec_driver_sql("CREATE TABLE future_native_schema (value TEXT)")

    monkeypatch.setattr(adoption, "_apply", changed_native_migration)
    destination = tmp_path / "drift.db"
    with pytest.raises(adoption.AdoptionError, match="native migration chain"):
        adoption.adopt_accounts_snapshot(published_snapshot, destination)
    assert not destination.exists()
