"""Synthetic native account audit privacy, transaction and migration checks."""

import io
import json
import runpy
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from superteacher.db import ROOT
from superteacher.models import AccountActionAudit, User
from tests.acct_util import H, build, sign_in
from tests.test_migrations import upgrade_to


def audit_rows(client):
    with client.app.state.session_factory() as db:
        return [dict(row._mapping) for row in db.execute(select(AccountActionAudit.__table__))]


def test_delete_retains_only_security_metadata_and_export_records_request(tmp_path, monkeypatch):
    from superteacher import account_audit

    fixed = datetime(2030, 7, 8, 23, 59, 17, 123456, tzinfo=UTC)

    class AuditClock:
        @staticmethod
        def now(tz):
            assert tz is UTC
            return fixed

    monkeypatch.setattr(account_audit, "datetime", AuditClock)
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "private@example.test")
        with c.app.state.session_factory() as db:
            uid = db.scalar(select(User.id).where(User.email == "private@example.test"))
        students = c.get("/api/students").json()
        c.post(f"/api/students/{students[0]['id']}/notes", json={"body": "SENTINEL private classroom"}, headers=H)
        exported = c.get("/api/account/export")
        assert exported.status_code == 200 and "SENTINEL private classroom" in exported.text
        before = audit_rows(c)
        assert len(before) == 1 and before[0]["action"] == "export" and before[0]["outcome"] == "requested"
        assert "account_action_audit" not in exported.text
        assert c.request("DELETE", "/api/account", json={"email": "private@example.test"}, headers=H).status_code == 204
        rows = audit_rows(c)
        assert {(row["action"], row["outcome"]) for row in rows} == {("export", "requested"), ("delete", "committed")}
        for row in rows:
            assert set(row) == {"event_id", "occurred_at", "actor_id", "target_id", "action", "outcome"}
            assert row["actor_id"] == row["target_id"] == uid
            assert len(row["event_id"]) == 32 and int(row["event_id"], 16)
            # SQLite loses tzinfo; its stored UTC wall time must still equal the known instant.
            persisted = row["occurred_at"]
            instant = persisted.replace(tzinfo=UTC) if persisted.tzinfo is None else persisted.astimezone(UTC)
            assert instant == fixed
        assert "@" not in json.dumps(rows, default=str) and "SENTINEL" not in json.dumps(rows, default=str)
        with c.app.state.session_factory() as db:
            assert db.get(User, uid) is None
        assert c.get("/api/account/export").status_code == 401
        assert len(audit_rows(c)) == 2


def test_refused_actions_do_not_create_trusted_audit_events(tmp_path):
    with build(tmp_path) as c:
        assert c.get("/api/account/export").status_code == 401
        assert c.request("DELETE", "/api/account", json={"email": "a@example.test"}, headers=H).status_code == 401
        sign_in(c, tmp_path, "a@example.test")
        assert c.request("DELETE", "/api/account", json={"email": "a@example.test"}).status_code == 403
        assert c.request("DELETE", "/api/account", json={"email": "other@example.test"}, headers=H).status_code == 422
        assert audit_rows(c) == []


@pytest.mark.parametrize("action", ["delete", "export"])
def test_audit_insert_failure_refuses_action_and_preserves_account(tmp_path, action):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.test")
        with c.app.state.session_factory() as db:
            db.execute(
                text(
                    "CREATE TRIGGER refuse_audit BEFORE INSERT ON account_action_audit "
                    "BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END"
                )
            )
            db.commit()
        with pytest.raises(IntegrityError):
            if action == "delete":
                c.request("DELETE", "/api/account", json={"email": "a@example.test"}, headers=H)
            else:
                c.get("/api/account/export")
        assert audit_rows(c) == []
        assert c.get("/api/overview").status_code == 200
        assert len(c.get("/api/students").json()) == 12


def test_commit_failure_rolls_back_delete_and_audit_together(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.test")
        sf = c.app.state.session_factory

        def refuse_commit(db):
            if db.scalar(select(func.count()).select_from(AccountActionAudit)):
                raise RuntimeError("synthetic commit refusal")

        event.listen(sf.class_, "before_commit", refuse_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic commit refusal"):
                c.request("DELETE", "/api/account", json={"email": "a@example.test"}, headers=H)
        finally:
            event.remove(sf.class_, "before_commit", refuse_commit)
        assert audit_rows(c) == []
        assert c.get("/api/overview").status_code == 200
        assert len(c.get("/api/students").json()) == 12


def test_native_0003_to_0004_upgrade_and_downgrade_are_additive(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    try:
        upgrade_to(engine, "0003")
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO users(id,email,created_at,disabled) "
                    "VALUES('kept','keep@example.test',CURRENT_TIMESTAMP,0)"
                )
            )
        before = set(inspect(engine).get_table_names())
        upgrade_to(engine, "0004")
        assert set(inspect(engine).get_table_names()) == before | {"account_action_audit"}
        assert inspect(engine).get_foreign_keys("account_action_audit") == []
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO account_action_audit "
                    "VALUES(:event,CURRENT_TIMESTAMP,'kept','kept','delete','committed')"
                ),
                {"event": "a" * 32},
            )
            db.execute(text("DELETE FROM users WHERE id='kept'"))
        with engine.connect() as db:
            assert db.execute(text("SELECT count(*) FROM account_action_audit")).scalar_one() == 1
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(
                text("INSERT INTO account_action_audit VALUES(:event,CURRENT_TIMESTAMP,'x','x','export','delivered')"),
                {"event": "b" * 32},
            )
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        with engine.connect() as db:
            cfg.attributes["connection"] = db
            command.downgrade(cfg, "0003")
            db.commit()
        assert set(inspect(engine).get_table_names()) == before
        with engine.connect() as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003"
    finally:
        engine.dispose()


def test_0004_ddl_compiles_for_postgres_without_user_foreign_keys():
    migration = runpy.run_path(str(ROOT / "alembic/versions/0004_account_audit.py"))
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    migration["upgrade"].__globals__["op"] = Operations(context)
    migration["upgrade"]()
    migration["downgrade"]()
    sql = output.getvalue()
    assert "CREATE TABLE account_action_audit" in sql and "DROP TABLE account_action_audit" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql and "REFERENCES" not in sql
    assert "'requested'" in sql and "'committed'" in sql


def test_purge_failure_rolls_back_already_inserted_event(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.test")
        with c.app.state.session_factory() as db:
            db.execute(
                text(
                    "CREATE TRIGGER refuse_delete BEFORE DELETE ON users "
                    "BEGIN SELECT RAISE(ABORT, 'synthetic purge failure'); END"
                )
            )
            db.commit()
        with pytest.raises(IntegrityError):
            c.request("DELETE", "/api/account", json={"email": "a@example.test"}, headers=H)
        assert audit_rows(c) == []
        assert c.get("/api/overview").status_code == 200
        assert len(c.get("/api/students").json()) == 12


def test_failed_export_is_still_only_a_request_event(tmp_path, monkeypatch):
    from superteacher import account_export

    def broken_stream(*args):
        yield b"{"
        raise RuntimeError("synthetic serialization failure")

    monkeypatch.setattr(account_export, "account_chunks", broken_stream)
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.test")
        with pytest.raises(RuntimeError, match="synthetic serialization failure"):
            c.get("/api/account/export")
        rows = audit_rows(c)
        assert len(rows) == 1 and rows[0]["action"] == "export" and rows[0]["outcome"] == "requested"
        assert c.get("/api/overview").status_code == 200
