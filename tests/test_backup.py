import os
import sqlite3
import stat
import threading
from contextlib import closing

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from superteacher import backup
from superteacher.db import Base
from superteacher.models import OWNER_EMAIL, OWNER_ID


def _relational_database(path):
    engine = create_engine(URL.create("sqlite", database=str(path)))
    Base.metadata.create_all(engine)
    engine.dispose()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO users (id, email, created_at, disabled) VALUES (?, ?, ?, ?)",
            (OWNER_ID, OWNER_EMAIL, "2026-10-01 12:00:00", False),
        )
        connection.execute(
            "INSERT INTO courses (id, name, owner_id) VALUES (?, ?, ?)", ("course", "Mathematics", OWNER_ID)
        )
        connection.executescript("""
            INSERT INTO sections (id, course_id, name) VALUES ('section', 'course', 'Period 1');
            INSERT INTO students (id, name, grade_level, section_id)
                VALUES ('student', 'Example Student', 8, 'section');
            INSERT INTO assessments (id, section_id, title, kind, max_points, due_date)
                VALUES ('assessment', 'section', 'Quiz', 'quiz', 100, '2026-10-01');
            INSERT INTO scores (id, assessment_id, student_id, points) VALUES ('score', 'assessment', 'student', 85);
            INSERT INTO attendance (id, student_id, day, status)
                VALUES ('attendance', 'student', '2026-10-01', 'present');
            INSERT INTO notes (id, student_id, body, created_at)
                VALUES ('note', 'student', 'Private example note', '2026-10-01 12:00:00');
            INSERT INTO insights (student_id, fingerprint, model, payload, created_at)
                VALUES ('student', 'fingerprint', 'example', '{"summary":"Private"}', '2026-10-01 12:00:00');
        """)


def _rows(path):
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            for table in (
                "users",
                "courses",
                "sections",
                "students",
                "assessments",
                "scores",
                "attendance",
                "notes",
                "insights",
            )
        }


def test_backup_and_recovery_preserve_all_relational_records(tmp_path):
    source = tmp_path / "source ?#.db"
    snapshot = tmp_path / "snapshot.db"
    restored = tmp_path / "rehearsal.db"
    _relational_database(source)
    before = source.read_bytes()

    backup.backup_database(source, snapshot)
    backup.backup_database(snapshot, restored)

    assert _rows(source) == _rows(snapshot) == _rows(restored)
    assert source.read_bytes() == before
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    with closing(sqlite3.connect(restored)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_live_wal_backup_is_consistent_during_writer_commit(tmp_path, monkeypatch):
    source = tmp_path / "live.db"
    destination = tmp_path / "snapshot.db"
    connect = sqlite3.connect
    with closing(connect(source)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
            CREATE TABLE parents (id INTEGER PRIMARY KEY, payload TEXT);
            CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id));
        """)
        connection.executemany("INSERT INTO parents VALUES (?, ?)", [(i, "x" * 8192) for i in range(600)])
        connection.executemany("INSERT INTO children VALUES (?, ?)", [(i, i) for i in range(600)])
        connection.commit()

    copying = threading.Event()
    committed = threading.Event()
    writer_errors = []

    def write():
        try:
            assert copying.wait(10)
            with closing(connect(source)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                with connection:
                    connection.execute("INSERT INTO parents VALUES (600, 'new record')")
                    connection.execute("INSERT INTO children VALUES (600, 600)")
            committed.set()
        except BaseException as error:
            writer_errors.append(error)
            committed.set()

    class ObservedConnection(sqlite3.Connection):
        def backup(self, target, **kwargs):
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                self.execute("INSERT INTO parents VALUES (999, 'must not write')")

            def progress(status, remaining, total):
                if not copying.is_set():
                    assert remaining > 0  # Writer commits while copying is still in progress.
                    copying.set()
                    assert committed.wait(10)

            return super().backup(target, progress=progress, **kwargs)

    def observed_connect(*args, **kwargs):
        if kwargs.get("uri"):
            kwargs["factory"] = ObservedConnection
        return connect(*args, **kwargs)

    monkeypatch.setattr(backup.sqlite3, "connect", observed_connect)
    writer = threading.Thread(target=write)
    writer.start()
    try:
        backup.backup_database(source, destination)
    finally:
        copying.set()
        writer.join(timeout=10)
    assert not writer.is_alive()
    assert not writer_errors
    assert committed.is_set()
    with closing(connect(destination)) as snapshot:
        parents = snapshot.execute("SELECT id FROM parents ORDER BY id").fetchall()
        children = snapshot.execute("SELECT parent_id FROM children ORDER BY parent_id").fetchall()
        assert parents == children
        assert len(parents) in (600, 601)
        assert snapshot.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert snapshot.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not os.path.exists(str(destination) + "-wal")


@pytest.mark.parametrize("kind", ["missing", "empty", "text", "corrupt", "directory"])
def test_invalid_source_never_creates_output(tmp_path, kind):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    if kind == "empty":
        source.touch()
    elif kind == "text":
        source.write_text("private invalid content")
    elif kind == "corrupt":
        source.write_bytes(b"SQLite format 3\x00" + b"invalid" * 100)
    elif kind == "directory":
        source.mkdir()
    before = source.read_bytes() if source.is_file() else None
    with pytest.raises(backup.BackupError):
        backup.backup_database(source, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".superteacher-backup-*"))
    if before is not None:
        assert source.read_bytes() == before
    elif kind == "missing":
        assert not source.exists()


@pytest.mark.parametrize("kind", ["existing", "same", "symlink", "hardlink", "dangling", "directory"])
def test_existing_destination_and_aliases_are_refused(tmp_path, kind):
    source = tmp_path / "source.db"
    _relational_database(source)
    destination = tmp_path / "destination.db"
    if kind == "same":
        destination = source
    elif kind == "symlink":
        destination.symlink_to(source)
    elif kind == "hardlink":
        os.link(source, destination)
    elif kind == "dangling":
        destination.symlink_to(tmp_path / "missing.db")
    elif kind == "directory":
        destination.mkdir()
    else:
        destination.write_text("keep existing content")
    before = source.read_bytes()
    with pytest.raises(backup.BackupError):
        backup.backup_database(source, destination)
    assert source.read_bytes() == before
    assert os.path.lexists(destination)
    if kind == "existing":
        assert destination.read_text() == "keep existing content"


def test_destination_parent_must_exist(tmp_path):
    source = tmp_path / "source.db"
    _relational_database(source)
    with pytest.raises(backup.BackupError, match="parent"):
        backup.backup_database(source, tmp_path / "absent" / "snapshot.db")
    assert not (tmp_path / "absent").exists()


def test_foreign_key_violation_is_rejected_without_exposing_records(tmp_path, capsys):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    _relational_database(source)
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("UPDATE notes SET student_id='private-orphan-id'")
        connection.commit()
    before = source.read_bytes()
    assert backup.main([str(source), str(destination)]) == 1
    output = capsys.readouterr()
    assert "foreign key validation failed" in output.err
    assert "private" not in output.err
    assert not output.out
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_integrity_constraint_violation_is_rejected(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE checked (value INTEGER CHECK(value > 0))")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("INSERT INTO checked VALUES (-1)")
        connection.commit()
    before = source.read_bytes()
    with pytest.raises(backup.BackupError, match="integrity validation failed"):
        backup.backup_database(source, destination)
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_interruption_cleans_temporary_files(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    _relational_database(source)
    before = source.read_bytes()

    def interrupt(connection):
        raise KeyboardInterrupt

    monkeypatch.setattr(backup, "_validate", interrupt)
    with pytest.raises(KeyboardInterrupt):
        backup.backup_database(source, destination)
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_destination_created_during_backup_is_never_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    _relational_database(source)
    validate = backup._validate

    def competing_publish(connection):
        validate(connection)
        destination.write_text("other operator's file")

    monkeypatch.setattr(backup, "_validate", competing_publish)
    with pytest.raises(backup.BackupError, match="already exists"):
        backup.backup_database(source, destination)
    assert destination.read_text() == "other operator's file"
    assert not list(tmp_path.glob(".superteacher-backup-*"))


def test_cli_reports_only_status(tmp_path, capsys):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    _relational_database(source)
    assert backup.main([str(source), str(destination)]) == 0
    output = capsys.readouterr()
    assert output.out == "Backup created and validated.\n"
    assert output.err == ""
