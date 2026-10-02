"""Operator CLI checks use actual native migrations and synthetic accounts only."""

import json
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from superteacher import db as database
from superteacher.accounts import resolve_session_hash


@pytest.fixture
def account_db(tmp_path):
    path = tmp_path / "accounts.db"
    engine = create_engine(f"sqlite:///{path}")
    database.run_migrations(engine)
    engine.dispose()
    with sqlite3.connect(path) as conn:
        for user, email in (("alice", "alice@example.invalid"), ("bob", "bob@example.invalid")):
            conn.execute(
                "INSERT INTO users (id,email,created_at,disabled) VALUES (?,?,CURRENT_TIMESTAMP,0)", (user, email)
            )
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,CURRENT_TIMESTAMP,'2099-01-01',CURRENT_TIMESTAMP)",
                (user + "-session-hash", user),
            )
            conn.execute(
                "INSERT INTO login_tokens VALUES (?,?,CURRENT_TIMESTAMP,'2099-01-01',NULL,NULL)",
                (user + "-login-hash", email),
            )
        conn.execute("INSERT INTO usage_counters VALUES ('alice','2026-10-02','chat',7)")
        conn.execute("INSERT INTO usage_counters VALUES ('bob','2026-10-02','chat',2)")
        conn.execute("INSERT INTO ai_budget VALUES ('2026-10-02',9)")
    return path


def run_cli(path, *args):
    return subprocess.run(
        [sys.executable, "-m", "superteacher.admin", "--database", str(path), *args],
        cwd=Path(__file__).resolve().parent.parent,
        text=True,
        capture_output=True,
        timeout=10,
    )


def rows(path, query):
    with sqlite3.connect(path) as conn:
        return conn.execute(query).fetchall()


def mutate(path, audit, action, user="alice"):
    return run_cli(path, action, user, "--actor", "operator-42", "--audit", str(audit))


def test_read_surface_does_not_change_records(account_db):
    before = account_db.read_bytes()
    result = run_cli(account_db, "list")
    assert result.returncode == 0, result.stderr
    users = {user["id"]: user for user in json.loads(result.stdout)["users"]}
    assert users["alice"]["email"] == "alice@example.invalid"
    assert users["alice"]["disabled"] is False
    result = run_cli(account_db, "usage", "alice", "--day", "2026-10-02")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "user_id": "alice",
        "day": "2026-10-02",
        "used": {"chat": 7, "insight": 0, "parent_update": 0},
    }
    assert account_db.read_bytes() == before


def test_disable_revokes_only_target_sessions_and_pending_links_and_keeps_usage(account_db, tmp_path):
    audit = tmp_path / "audit.jsonl"
    result = mutate(account_db, audit, "disable")
    assert result.returncode == 0, result.stderr
    assert rows(account_db, "SELECT id,disabled FROM users WHERE id IN ('alice','bob') ORDER BY id") == [
        ("alice", 1),
        ("bob", 0),
    ]
    assert rows(account_db, "SELECT user_id FROM sessions") == [("bob",)]
    assert rows(account_db, "SELECT email FROM login_tokens") == [("bob@example.invalid",)]
    assert rows(account_db, "SELECT count FROM usage_counters ORDER BY user_id") == [(7,), (2,)]
    assert rows(account_db, "SELECT count FROM ai_budget") == [(9,)]
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert [record["phase"] for record in records] == ["intent", "committed"]
    assert records[0]["event_id"] == records[1]["event_id"]
    assert all(record["actor_id"] == "operator-42" and record["user_id"] == "alice" for record in records)
    assert "@" not in audit.read_text() and "hash" not in audit.read_text()
    assert audit.stat().st_mode & 0o777 == 0o600
    assert mutate(account_db, audit, "enable").returncode == 0
    assert rows(account_db, "SELECT disabled FROM users WHERE id='alice'") == [(0,)]
    assert rows(account_db, "SELECT user_id FROM sessions") == [("bob",)]


def test_signout_revokes_pending_links_without_disabling(account_db, tmp_path):
    result = mutate(account_db, tmp_path / "audit.jsonl", "sign-out")
    assert result.returncode == 0, result.stderr
    assert rows(account_db, "SELECT disabled FROM users WHERE id='alice'") == [(0,)]
    assert rows(account_db, "SELECT user_id FROM sessions") == [("bob",)]
    assert rows(account_db, "SELECT email FROM login_tokens") == [("bob@example.invalid",)]


def test_existing_auth_resolver_observes_revocation_and_other_user_keeps_access(account_db, tmp_path):
    engine = create_engine(f"sqlite:///{account_db}")
    try:
        with Session(engine) as session:
            user = resolve_session_hash(session, "alice-session-hash", idle=timedelta(hours=72), touch=False)
            assert user.id == "alice"
        assert mutate(account_db, tmp_path / "audit.jsonl", "sign-out").returncode == 0
        with Session(engine) as session:
            assert resolve_session_hash(session, "alice-session-hash", idle=timedelta(hours=72), touch=False) is None
            assert resolve_session_hash(session, "bob-session-hash", idle=timedelta(hours=72), touch=False).id == "bob"
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure_phase,exit_code,disabled", [("intent", 2, 0), ("committed", 3, 1)])
def test_audit_failure_distinguishes_rollback_from_committed_change(
    account_db, tmp_path, monkeypatch, capsys, failure_phase, exit_code, disabled
):
    from superteacher import admin

    append = admin.AuditLog.append

    def fail(log, record):
        if record["phase"] == failure_phase:
            raise OSError("synthetic disk failure")
        append(log, record)

    monkeypatch.setattr(admin.AuditLog, "append", fail)
    audit = tmp_path / "audit.jsonl"
    code = admin.main(
        ["--database", str(account_db), "disable", "alice", "--actor", "operator-42", "--audit", str(audit)]
    )
    assert code == exit_code
    assert rows(account_db, "SELECT disabled FROM users WHERE id='alice'") == [(disabled,)]
    assert rows(account_db, "SELECT COUNT(*) FROM sessions WHERE user_id='alice'") == [(1 - disabled,)]
    error = capsys.readouterr().err
    if disabled:
        assert "COMMITTED" in error and "before any retry" in error
        assert [json.loads(line)["phase"] for line in audit.read_text().splitlines()] == ["intent"]
    else:
        assert audit.read_bytes() == b""


def test_database_failure_rolls_back_all_changes_and_records_outcome(account_db, tmp_path):
    with sqlite3.connect(account_db) as conn:
        conn.execute("CREATE TRIGGER reject_disable BEFORE UPDATE ON users BEGIN SELECT RAISE(ABORT,'private'); END")
    audit = tmp_path / "audit.jsonl"
    result = mutate(account_db, audit, "disable")
    assert result.returncode == 2 and "private" not in result.stderr
    assert rows(account_db, "SELECT disabled FROM users WHERE id='alice'") == [(0,)]
    assert rows(account_db, "SELECT COUNT(*) FROM sessions") == [(2,)]
    assert rows(account_db, "SELECT COUNT(*) FROM login_tokens") == [(2,)]
    assert [json.loads(line)["phase"] for line in audit.read_text().splitlines()] == ["intent", "rolled_back"]


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_sqlite_sidecar_cannot_be_used_as_audit_log(account_db, suffix):
    with sqlite3.connect(account_db) as conn:
        assert conn.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",)
    audit = Path(str(account_db) + suffix)
    before = account_db.read_bytes()
    result = mutate(account_db, audit, "disable")
    assert result.returncode == 2
    assert account_db.read_bytes() == before
    assert not audit.exists()


@pytest.mark.parametrize("action", ["disable", "enable", "sign-out"])
def test_mutations_require_actor_and_audit(account_db, action):
    before = account_db.read_bytes()
    assert run_cli(account_db, action, "alice").returncode != 0
    assert account_db.read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "empty", "behind", "missing-table"])
def test_unqualified_database_is_refused_without_creation_or_migration(account_db, tmp_path, kind):
    if kind == "missing":
        path = tmp_path / "missing.db"
    elif kind == "empty":
        path = tmp_path / "empty.db"
        path.touch()
    else:
        path = account_db
        with sqlite3.connect(path) as conn:
            if kind == "behind":
                conn.execute("UPDATE alembic_version SET version_num='0002'")
            else:
                conn.execute("DROP TABLE usage_counters")
    before = path.read_bytes() if path.exists() else None
    result = mutate(path, tmp_path / "audit.jsonl", "disable")
    assert result.returncode != 0
    assert (path.read_bytes() if path.exists() else None) == before
    assert not (tmp_path / "audit.jsonl").exists()


@pytest.mark.parametrize("target", ["unknown", "owner0000000", "alice' OR 1=1 --"])
def test_invalid_target_preserves_database(account_db, tmp_path, target):
    before = account_db.read_bytes()
    result = mutate(account_db, tmp_path / "audit.jsonl", "disable", target)
    assert result.returncode != 0
    assert account_db.read_bytes() == before


@pytest.mark.parametrize("kind", ["public", "symlink", "database", "incomplete", "hardlink"])
def test_unsafe_audit_target_refused_before_mutation(account_db, tmp_path, kind):
    audit = tmp_path / "audit.jsonl"
    if kind == "public":
        audit.write_text("keep\n")
        audit.chmod(0o644)
    elif kind == "symlink":
        destination = tmp_path / "keep"
        destination.write_text("keep\n")
        audit.symlink_to(destination)
    elif kind == "database":
        audit = account_db
        audit.chmod(0o600)
    elif kind == "incomplete":
        audit.write_text('{"partial":')
        audit.chmod(0o600)
    else:
        audit.hardlink_to(account_db)
        account_db.chmod(0o600)
    before = account_db.read_bytes()
    audit_before = audit.read_bytes()
    assert mutate(account_db, audit, "disable").returncode != 0
    assert account_db.read_bytes() == before
    assert audit.read_bytes() == audit_before


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_list_pages_are_ordered_bounded_and_exclude_passcode_owner(account_db, limit):
    with sqlite3.connect(account_db) as conn:
        for user in ("zoe", "charlie", "owner0000000"):
            conn.execute(
                "INSERT INTO users (id,email,created_at,disabled) VALUES (?,?,CURRENT_TIMESTAMP,1)",
                (user, user + "@example.invalid"),
            )
    before = account_db.read_bytes()
    found = []
    after = None
    while True:
        args = ["list", "--limit", str(limit)]
        if after is not None:
            args += ["--after", after]
        result = run_cli(account_db, *args)
        assert result.returncode == 0, result.stderr
        page = json.loads(result.stdout)
        assert set(page) == {"users", "next_cursor"}
        assert 0 < len(page["users"]) <= limit
        assert all(isinstance(user["disabled"], bool) for user in page["users"])
        found.extend(user["id"] for user in page["users"])
        after = page["next_cursor"]
        if after is None:
            break
        assert after == page["users"][-1]["id"]
    assert found == ["alice", "bob", "charlie", "zoe"]
    assert account_db.read_bytes() == before


def test_list_default_limit_exact_boundary_and_empty_tail(account_db):
    with sqlite3.connect(account_db) as conn:
        conn.executemany(
            "INSERT INTO users (id,email,created_at,disabled) VALUES (?,?,CURRENT_TIMESTAMP,0)",
            [(f"user{i:03}", f"user{i:03}@example.invalid") for i in range(99)],
        )
    first = json.loads(run_cli(account_db, "list").stdout)
    assert len(first["users"]) == 100 and first["next_cursor"] == "user097"
    final = json.loads(run_cli(account_db, "list", "--after", first["next_cursor"]).stdout)
    assert [user["id"] for user in final["users"]] == ["user098"]
    assert final["next_cursor"] is None
    boundary = json.loads(run_cli(account_db, "list", "--limit", "101").stdout)
    assert len(boundary["users"]) == 101 and boundary["next_cursor"] is None
    assert json.loads(run_cli(account_db, "list", "--after", "zzzz").stdout) == {"users": [], "next_cursor": None}


@pytest.mark.parametrize(
    "option,value",
    [
        ("--limit", "0"),
        ("--limit", "-1"),
        ("--limit", "1001"),
        ("--limit", "oops"),
        ("--after", ""),
        ("--after", "alice@example.invalid"),
        ("--after", "a" * 65),
        ("--after", "alice' OR 1=1 --"),
        ("--after", "é"),
    ],
)
def test_list_invalid_bounds_and_cursor_refused_before_open(tmp_path, option, value):
    path = tmp_path / "missing.db"
    result = run_cli(path, "list", option, value)
    assert result.returncode == 2
    assert not path.exists()
    assert "Cannot open" not in result.stderr


def test_list_query_fetches_only_limit_plus_one_and_binds_cursor():
    from superteacher import admin

    class BoundedCursor:
        closed = False

        def fetchall(self):
            assert "LIMIT ?" in query
            assert parameters == ("owner0000000", "cursor:1", 3)
            return [{"id": str(i), "disabled": i % 2} for i in range(parameters[-1])]

        def close(self):
            self.closed = True

    cursor = BoundedCursor()

    class Connection:
        def execute(self, sql, values):
            nonlocal query, parameters
            query, parameters = sql, values
            return cursor

    query = parameters = None
    page = admin._list_users(Connection(), limit=2, after="cursor:1")
    assert "id > ?" in query and "ORDER BY id" in query
    assert [user["id"] for user in page["users"]] == ["0", "1"]
    assert page["next_cursor"] == "1" and cursor.closed


def test_list_deleted_cursor_and_concurrent_insert_semantics(account_db):
    first = json.loads(run_cli(account_db, "list", "--limit", "1").stdout)
    with sqlite3.connect(account_db) as conn:
        conn.execute("DELETE FROM sessions WHERE user_id='alice'")
        conn.execute("DELETE FROM users WHERE id='alice'")
        for user in ("aaron", "anna"):
            conn.execute(
                "INSERT INTO users (id,email,created_at,disabled) VALUES (?,?,CURRENT_TIMESTAMP,0)",
                (user, user + "@example.invalid"),
            )
    page = json.loads(run_cli(account_db, "list", "--after", first["next_cursor"]).stdout)
    assert [user["id"] for user in page["users"]] == ["anna", "bob"]
    assert page["next_cursor"] is None
