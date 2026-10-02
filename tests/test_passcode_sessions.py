"""Passcode signatures are only one gate: session rows authorize the owner."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from superteacher import accounts, auth
from superteacher.models import OWNER_ID, AuthSession, User
from tests.sec_util import H, build, login


def probe(c, token):
    c.cookies.clear()
    c.cookies.set(auth.COOKIE, token)
    return c.get("/api/auth/me").status_code


def test_rotation_and_independent_browser(monkeypatch):
    monkeypatch.setattr("itsdangerous.TimestampSigner.get_timestamp", lambda self: 1_800_000_000)
    with build() as c:
        first = login(c).cookies[auth.COOKIE]
        independent = TestClient(c.app)
        second = login(independent).cookies[auth.COOKIE]
        replacement = login(c).cookies[auth.COOKIE]
        assert replacement != first
        assert probe(c, first) == 401
        assert probe(c, replacement) == 200
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        assert probe(independent, second) == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"v": 1},
        {"v": True, "mode": "passcode", "nonce": "A" * 43},
        {"v": 2, "mode": "accounts", "nonce": "A" * 43},
        {"v": 2, "mode": "passcode", "nonce": "A" * 42},
        {"v": 2, "mode": "passcode", "nonce": "A" * 43, "extra": 1},
    ],
)
def test_strict_signed_payload_rejected(payload):
    with build() as c:
        assert probe(c, c.app.state.auth.serializer.dumps(payload)) == 401


def test_signed_cookie_requires_matching_owner_row():
    with build() as c:
        assert probe(c, c.app.state.auth.issue()) == 401
        token = login(c).cookies[auth.COOKIE]
        with c.app.state.session_factory() as db:
            db.add(User(id="other", email="other@example.com"))
            db.execute(update(AuthSession).values(user_id="other", expires_at=accounts.now() - timedelta(seconds=1)))
            db.commit()
        assert probe(c, token) == 401
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        with c.app.state.session_factory() as db:
            assert db.get(AuthSession, accounts.hash_secret(token)).user_id == "other"
        c.cookies.clear()
        c.cookies.set(auth.COOKIE, token)
        assert login(c).status_code == 200
        with c.app.state.session_factory() as db:
            assert db.get(AuthSession, accounts.hash_secret(token)).user_id == "other"


@pytest.mark.parametrize("change", ["absolute", "idle", "disabled"])
def test_database_lifetime_and_disabled_owner(change):
    with build(accounts_session_idle_hours=1) as c:
        token = login(c).cookies[auth.COOKIE]
        with c.app.state.session_factory() as db:
            row = db.get(AuthSession, accounts.hash_secret(token))
            assert row is not None
            assert accounts.aware(row.expires_at) - accounts.aware(row.created_at) == timedelta(hours=12)
            if change == "absolute":
                row.expires_at = accounts.now() - timedelta(seconds=1)
            elif change == "idle":
                row.last_seen_at = accounts.now() - timedelta(hours=2)
            else:
                db.get(User, OWNER_ID).disabled = True
            db.commit()
        assert probe(c, token) == 401


def test_failed_password_and_csrf_cannot_revoke():
    with build() as c:
        token = login(c).cookies[auth.COOKIE]
        assert login(c, "wrong").status_code == 401
        assert c.post("/api/auth/logout").status_code == 403
        assert c.post("/api/auth/logout", headers={**H, "Origin": "https://evil.example"}).status_code == 403
        assert probe(c, token) == 200


def test_strict_signer_checks_format_without_database():
    with build() as c:
        st = c.app.state.auth
        assert st.valid(st.issue())
        for payload in (
            {"v": 1},
            [],
            {"v": True, "mode": "passcode", "nonce": "A" * 43},
            {"v": 2, "mode": "passcode", "nonce": "A" * 43, "extra": 1},
            {"v": 2, "mode": "passcode", "nonce": "." * 43},
        ):
            assert not st.valid(st.serializer.dumps(payload))
        assert not st.valid("A" * 513)


def test_rotation_insert_failure_rolls_back_revocation(monkeypatch):
    from sqlalchemy import event

    with build(raise_server_exceptions=False) as c:
        old = login(c).cookies[auth.COOKIE]
        engine = c.app.state.session_factory.kw["bind"]

        def fail_insert(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO SESSIONS"):
                raise RuntimeError("injected insert failure")

        event.listen(engine, "before_cursor_execute", fail_insert)
        try:
            response = login(c)
            assert response.status_code == 500
            assert "set-cookie" not in response.headers
        finally:
            event.remove(engine, "before_cursor_execute", fail_insert)
        assert probe(c, old) == 200
        with c.app.state.session_factory() as db:
            assert len(db.scalars(select(AuthSession)).all()) == 1


def test_database_failure_never_falls_back_to_signature(monkeypatch):
    with build(raise_server_exceptions=False) as c:
        old = login(c).cookies[auth.COOKIE]
        original = c.app.state.session_factory

        def unavailable():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(c.app.state, "session_factory", unavailable)
        for response in (
            login(c),
            c.get("/api/auth/me"),
            c.get("/api/overview"),
            c.post("/api/auth/logout", headers=H),
        ):
            assert response.status_code == 500
            assert "set-cookie" not in response.headers
        monkeypatch.setattr(c.app.state, "session_factory", original)
        assert probe(c, old) == 200


def test_cross_mode_and_adopted_owner_cookies(tmp_path):
    from tests.acct_util import build as accounts_build

    with build() as c, accounts_build(tmp_path) as account_client:
        token = login(c).cookies[auth.COOKIE]
        nonce = c.app.state.auth.serializer.loads(token)["nonce"]
        factory = c.app.state.session_factory
        # Run accounts policy on the very same DB, including an adopted owner.
        account_client.app.state.session_factory = factory
        with factory() as db:
            owner = db.get(User, OWNER_ID)
            owner.email = "adopted@example.com"
            raw = accounts.create_session(db, account_client.app.state.auth.settings, owner)
        assert probe(account_client, token) == 401
        assert probe(account_client, nonce) == 401
        # Even a planted hash for a malformed opaque wire value cannot authenticate accounts.
        for value in (token, "A" * 42, "A" * 44, "." * 43):
            with factory() as db:
                if db.get(AuthSession, accounts.hash_secret(value)) is None:
                    t = accounts.now()
                    db.add(
                        AuthSession(
                            id_hash=accounts.hash_secret(value),
                            user_id=OWNER_ID,
                            created_at=t,
                            last_seen_at=t,
                            expires_at=t + timedelta(hours=1),
                        )
                    )
                    db.commit()
            assert probe(account_client, value) == 401
        assert probe(account_client, raw) == 200
        assert auth._resolve(account_client.app.state.auth, factory, raw).is_legacy is False
        assert auth._resolve(c.app.state.auth, factory, token).is_legacy is True
        assert probe(c, raw) == 401
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        assert probe(account_client, raw) == 200
        # Accounts logout cannot erase a signed passcode wrapper's row.
        account_client.cookies.clear()
        account_client.cookies.set(auth.COOKIE, token)
        assert account_client.post("/api/auth/logout", headers=H).status_code == 200
        assert probe(c, token) == 200
        from tests.acct_util import sign_in

        account_client.cookies.clear()
        account_client.cookies.set(auth.COOKIE, token)
        sign_in(account_client, tmp_path, "adopted@example.com")
        assert probe(c, token) == 200
        # Passcode re-login with a planted account cookie preserves that account row.
        c.cookies.clear()
        c.cookies.set(auth.COOKIE, raw)
        assert login(c).status_code == 200
        assert probe(account_client, raw) == 200


def test_restart_same_database_and_different_database(tmp_path):
    from sqlalchemy.orm import sessionmaker

    from superteacher.config import Settings
    from superteacher.db import make_engine
    from superteacher.main import create_app

    settings = Settings(auth_password="correct horse", auth_disabled=False, session_secret="s" * 32)

    def app_at(path):
        engine = make_engine(f"sqlite:///{path}")
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        return create_app(session_factory=factory, engine=engine, seed=False, settings=settings), engine

    app, first_engine = app_at(tmp_path / "shared.db")
    with TestClient(app) as c:
        token = login(c).cookies[auth.COOKIE]
    first_engine.dispose()
    restarted, second_engine = app_at(tmp_path / "shared.db")
    empty, empty_engine = app_at(tmp_path / "different.db")
    with TestClient(restarted) as c, TestClient(empty) as other:
        assert probe(c, token) == 200
        assert probe(other, token) == 401
    second_engine.dispose()
    empty_engine.dispose()


def test_poll_is_read_only_and_activity_touches(monkeypatch):
    with build(accounts_session_idle_hours=1) as c:
        token = login(c).cookies[auth.COOKIE]
        st, factory = c.app.state.auth, c.app.state.session_factory
        original_time = accounts.now() - timedelta(minutes=50)
        with factory() as db:
            row = db.get(AuthSession, accounts.hash_secret(token))
            row.last_seen_at = original_time
            db.commit()
        assert auth._resolve(st, factory, token, touch=False) is not None
        with factory() as db:
            assert accounts.aware(db.get(AuthSession, accounts.hash_secret(token)).last_seen_at) == original_time
        assert auth._resolve(st, factory, token, touch=True) is not None
        with factory() as db:
            assert accounts.now() - accounts.aware(
                db.get(AuthSession, accounts.hash_secret(token)).last_seen_at
            ) < timedelta(minutes=1)
        # The idle cap cannot exceed the passcode absolute TTL, even for inconsistent/future rows.
        with factory() as db:
            row = db.get(AuthSession, accounts.hash_secret(token))
            row.last_seen_at = accounts.now() - timedelta(hours=13)
            row.expires_at = accounts.now() + timedelta(days=1)
            db.commit()
        st.settings.accounts_session_idle_hours = 720
        assert auth._resolve(st, factory, token, touch=False) is None
        with factory() as db:
            assert db.get(AuthSession, accounts.hash_secret(token)) is not None


@pytest.mark.parametrize("race", ["logout", "newer_touch", "expiry_refresh"])
def test_session_mutation_races_use_current_database_predicates(tmp_path, race):
    from sqlalchemy import create_engine, delete, event
    from sqlalchemy.orm import sessionmaker

    from superteacher.db import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    independent = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    token = "A" * 43
    t = accounts.now()
    seen = t - timedelta(hours=2) if race == "expiry_refresh" else t - timedelta(minutes=5)
    with factory() as db:
        accounts.ensure_owner(db)
        db.add(
            AuthSession(
                id_hash=accounts.hash_secret(token),
                user_id=OWNER_ID,
                created_at=t,
                last_seen_at=seen,
                expires_at=t + timedelta(hours=12),
            )
        )
        db.commit()
    refreshed = t + timedelta(seconds=10)

    def intervene(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("UPDATE SESSIONS", "DELETE FROM SESSIONS")):
            with independent.begin() as other:
                if race == "logout":
                    other.execute(delete(AuthSession))
                else:
                    other.execute(update(AuthSession).values(last_seen_at=refreshed))

    event.listen(engine, "before_cursor_execute", intervene)
    try:
        with factory() as db:
            user = accounts.resolve_session_hash(
                db, accounts.hash_secret(token), idle=timedelta(hours=1), required_owner=OWNER_ID
            )
            if race == "logout":
                assert user is None
    finally:
        event.remove(engine, "before_cursor_execute", intervene)
    with factory() as db:
        row = db.get(AuthSession, accounts.hash_secret(token))
        if race == "logout":
            assert row is None
        else:
            assert row is not None
            assert accounts.aware(row.last_seen_at) == refreshed
    engine.dispose()
    independent.dispose()


def file_client(tmp_path, **kw):
    from sqlalchemy.orm import sessionmaker

    from superteacher.config import Settings
    from superteacher.db import make_engine
    from superteacher.main import create_app

    engine = make_engine(f"sqlite:///{tmp_path / 'websocket.db'}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(auth_password="correct horse", auth_disabled=False, session_secret="s" * 32, **kw)
    return TestClient(create_app(session_factory=factory, engine=engine, seed=False, settings=settings)), engine


@pytest.mark.parametrize("change", ["logout", "absolute", "idle", "disabled"])
def test_idle_websocket_closes_on_database_session_end(tmp_path, change):
    from starlette.websockets import WebSocketDisconnect

    client, engine = file_client(tmp_path, accounts_session_idle_hours=1)
    with client as c:
        token = login(c).cookies[auth.COOKIE]
        with c.websocket_connect("/api/chat/ws") as ws:
            with c.app.state.session_factory() as db:
                row = db.get(AuthSession, accounts.hash_secret(token))
                if change == "absolute":
                    row.expires_at = accounts.now() - timedelta(seconds=1)
                elif change == "idle":
                    row.last_seen_at = accounts.now() - timedelta(hours=2)
                elif change == "disabled":
                    db.get(User, OWNER_ID).disabled = True
                db.commit()
            if change == "logout":
                assert c.post("/api/auth/logout", headers=H).status_code == 200
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008
    engine.dispose()


def test_logout_cancels_actual_provider_and_releases_original_loop_permit(tmp_path, monkeypatch):
    import asyncio

    from starlette.websockets import WebSocketDisconnect

    from superteacher import ai, ai_capacity
    from tests.ai_fakes import FakeAI, FakeStream

    class BlockedStream(FakeStream):
        @property
        def text_stream(self):
            async def generate():
                yield "started"
                await asyncio.Event().wait()

            return generate()

    stream = BlockedStream([], "end_turn", [])
    fake = FakeAI([stream])
    monkeypatch.setattr(ai, "client", lambda: fake)
    client, engine = file_client(tmp_path)

    async def original_loop_active():
        return ai_capacity._budgets[asyncio.get_running_loop()].active

    with client as c:
        login(c)
        with c.websocket_connect("/api/chat/ws") as ws:
            ws.send_json({"content": "start provider"})
            assert ws.receive_json() == {"type": "delta", "text": "started"}
            assert c.portal.call(original_loop_active) == 1
            assert c.post("/api/auth/logout", headers=H).status_code == 200
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008
            assert stream.closed
            assert fake.close_calls == 1
            assert c.portal.call(original_loop_active) == 0
    engine.dispose()


def test_websocket_poll_and_reset_preserve_idle_timestamp(tmp_path):
    import time

    client, engine = file_client(tmp_path)
    with client as c:
        token = login(c).cookies[auth.COOKIE]
        with c.websocket_connect("/api/chat/ws") as ws:
            old = accounts.now() - timedelta(minutes=50)
            with c.app.state.session_factory() as db:
                db.execute(update(AuthSession).values(last_seen_at=old))
                db.commit()
            ws.send_json({"type": "reset"})
            # More than one watcher interval; no user message is sent.
            time.sleep(1.2)
            with c.app.state.session_factory() as db:
                assert accounts.aware(db.get(AuthSession, accounts.hash_secret(token)).last_seen_at) == old
    engine.dispose()


def test_correctly_signed_malformed_serializer_payload_is_rejected():
    import base64

    with build() as c:
        st = c.app.state.auth
        for payload in (base64.urlsafe_b64encode(b"not JSON").rstrip(b"="), b".eA"):
            malformed = st.serializer.make_signer().sign(payload).decode()
            assert not st.valid(malformed)
            assert probe(c, malformed) == 401


def test_login_purges_expired_owner_rows_without_evicting_other_users():
    with build(accounts_session_idle_hours=1) as c:
        expired = login(c).cookies[auth.COOKIE]
        with c.app.state.session_factory() as db:
            db.get(AuthSession, accounts.hash_secret(expired)).expires_at = accounts.now() - timedelta(seconds=1)
            other = User(id="other", email="other@example.com")
            db.add(other)
            opaque = accounts.create_session(db, c.app.state.auth.settings, other)
        c.cookies.clear()
        assert login(c).status_code == 200
        with c.app.state.session_factory() as db:
            assert db.get(AuthSession, accounts.hash_secret(expired)) is None
            assert db.get(AuthSession, accounts.hash_secret(opaque)) is not None


def test_disabled_owner_is_not_reenabled_by_login():
    with build() as c:
        login(c)
        with c.app.state.session_factory() as db:
            db.get(User, OWNER_ID).disabled = True
            db.commit()
        assert login(c).status_code == 401
        with c.app.state.session_factory() as db:
            assert db.get(User, OWNER_ID).disabled is True


def test_passcode_login_preserves_adopted_owner_accounts_idle_policy(tmp_path):
    from tests.acct_util import build as accounts_build

    with build() as c, accounts_build(tmp_path) as other:
        assert login(c).status_code == 200
        factory = c.app.state.session_factory
        with factory() as db:
            raw = accounts.create_session(db, other.app.state.auth.settings, db.get(User, OWNER_ID))
            db.get(AuthSession, accounts.hash_secret(raw)).last_seen_at = accounts.now() - timedelta(hours=13)
            db.commit()
        c.cookies.clear()
        assert login(c).status_code == 200
        other.app.state.session_factory = factory
        assert probe(other, raw) == 200


def test_rotation_commit_failure_rolls_back_existing_session(monkeypatch):
    from sqlalchemy import event

    with build(raise_server_exceptions=False) as c:
        token = login(c).cookies[auth.COOKIE]
        factory = c.app.state.session_factory

        def fail_commit(db):
            raise RuntimeError("injected commit failure")

        event.listen(factory, "before_commit", fail_commit)
        try:
            response = login(c)
            assert response.status_code == 500
            assert "set-cookie" not in response.headers
        finally:
            event.remove(factory, "before_commit", fail_commit)
        assert probe(c, token) == 200
        with factory() as db:
            assert len(db.scalars(select(AuthSession)).all()) == 1
