"""Server-side session lifecycle: flags, rotation, idle/absolute expiry, revocation (F-06), logout-all."""

from datetime import timedelta

from sqlalchemy import func, select, update

from superteacher import accounts
from superteacher.models import AuthSession, User
from tests.acct_util import H, build, request_link, second_client, sign_in


def _sessions(c) -> int:
    with c.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(AuthSession))


def test_cookie_flags_and_opacity(tmp_path):
    with build(tmp_path, cookie_secure=True) as c:
        request_link(c, "a@example.com")
        from tests.acct_util import outbox, token_from, verify

        r = verify(c, token_from(outbox(tmp_path)[-1]))
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "secure" in cookie
        assert "max-age=" in cookie
        raw = c.cookies.get("st_session")
        assert len(raw) >= 43  # 256 bits, url-safe
        assert "a@example.com" not in raw


def test_cookie_not_secure_on_plain_http_by_default(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        from tests.acct_util import outbox, token_from, verify

        r = verify(c, token_from(outbox(tmp_path)[-1]))
        assert "secure" not in r.headers["set-cookie"].lower()


def test_login_rotates_the_session_and_kills_a_planted_cookie(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        old = c.cookies.get("st_session")
        sign_in(c, tmp_path, "a@example.com")  # signing in again while holding a session
        new = c.cookies.get("st_session")
        assert new != old and _sessions(c) == 1  # the old server-side row is gone
        other = second_client(c)
        other.cookies.set("st_session", old)
        assert other.get("/api/overview").status_code == 401


def test_idle_expiry(tmp_path):
    with build(tmp_path, accounts_session_idle_hours=1) as c:
        sign_in(c, tmp_path, "a@example.com")
        assert c.get("/api/auth/me").status_code == 200
        with c.app.state.session_factory() as db:
            db.execute(update(AuthSession).values(last_seen_at=accounts.now() - timedelta(hours=2)))
            db.commit()
        assert c.get("/api/overview").status_code == 401
        assert _sessions(c) == 0  # lazily purged


def test_activity_keeps_a_session_alive_within_idle_window(tmp_path):
    with build(tmp_path, accounts_session_idle_hours=1) as c:
        sign_in(c, tmp_path, "a@example.com")
        with c.app.state.session_factory() as db:
            db.execute(update(AuthSession).values(last_seen_at=accounts.now() - timedelta(minutes=50)))
            db.commit()
        assert c.get("/api/overview").status_code == 200  # touched: last_seen_at moves forward
        with c.app.state.session_factory() as db:
            seen = accounts.aware(db.scalar(select(AuthSession.last_seen_at)))
            assert accounts.now() - seen < timedelta(minutes=1)


def test_absolute_expiry_even_when_active(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        with c.app.state.session_factory() as db:
            db.execute(update(AuthSession).values(expires_at=accounts.now() - timedelta(seconds=1)))
            db.commit()
        assert c.get("/api/overview").status_code == 401


def test_absolute_lifetime_is_configurable_and_matches_cookie(tmp_path):
    with build(tmp_path, accounts_session_absolute_hours=2) as c:
        from tests.acct_util import outbox, request_link, token_from, verify

        request_link(c, "a@example.com")
        r = verify(c, token_from(outbox(tmp_path)[-1]))
        assert "max-age=7200" in r.headers["set-cookie"].lower()


def test_logout_revokes_server_side_so_a_copied_cookie_is_dead(tmp_path):
    """F-06: the old stateless cookie survived logout for hours."""
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        copied = c.cookies.get("st_session")
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        thief = second_client(c)
        thief.cookies.set("st_session", copied)
        assert thief.get("/api/overview").status_code == 401
        assert thief.get("/api/auth/me").status_code == 401
        assert _sessions(c) == 0


def test_logout_needs_csrf_header(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        assert c.post("/api/auth/logout").status_code == 403
        assert c.get("/api/overview").status_code == 200


def test_logout_all_ends_every_browser(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        phone = second_client(c)
        sign_in(phone, tmp_path, "a@example.com")
        bob = second_client(c)
        sign_in(bob, tmp_path, "b@example.com")
        assert _sessions(c) == 3
        assert c.post("/api/auth/logout-all", headers=H).status_code == 200
        assert c.get("/api/overview").status_code == 401 and phone.get("/api/overview").status_code == 401
        assert bob.get("/api/overview").status_code == 200  # another user is untouched


def test_logout_all_requires_a_session_and_csrf(tmp_path):
    with build(tmp_path) as c:
        assert c.post("/api/auth/logout-all", headers=H).status_code == 401
        sign_in(c, tmp_path, "a@example.com")
        assert c.post("/api/auth/logout-all").status_code == 403


def test_disabled_user_loses_access_immediately_and_cannot_sign_in(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        with c.app.state.session_factory() as db:
            db.execute(update(User).values(disabled=True))
            db.commit()
        assert c.get("/api/overview").status_code == 401
        from tests.acct_util import outbox, request_link, token_from, verify

        request_link(c, "a@example.com")
        assert verify(c, token_from(outbox(tmp_path)[-1])).status_code == 400


def test_forged_and_oversized_cookies(tmp_path):
    with build(tmp_path) as c:
        for v in ("forged", "x" * 10_000, "a.b.c", "'; drop table sessions;--"):
            c.cookies.set("st_session", v)
            assert c.get("/api/overview").status_code == 401, v[:20]


def test_websocket_requires_a_live_session(tmp_path):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with build(tmp_path) as c:
        with pytest.raises(WebSocketDisconnect), c.websocket_connect("/api/chat/ws"):
            pass
        sign_in(c, tmp_path, "a@example.com")
        with c.websocket_connect("/api/chat/ws") as ws:
            ws.send_json({"type": "reset"})
        c.post("/api/auth/logout", headers=H)
        with pytest.raises(WebSocketDisconnect), c.websocket_connect("/api/chat/ws"):
            pass


def test_passcode_endpoint_is_not_available_in_accounts_mode(tmp_path):
    with build(tmp_path) as c:
        assert c.post("/api/auth/login", json={"password": "x"}, headers=H).status_code == 404
        assert c.get("/api/auth/config").json() == {"auth_mode": "accounts", "email_available": True}


def test_accounts_endpoints_are_404_in_passcode_mode():
    from tests.sec_util import build as build_passcode

    with build_passcode() as c:
        assert request_link(c, "a@example.com").status_code == 404
        assert c.post("/api/auth/verify", json={"token": "x" * 30}, headers=H).status_code == 404
        assert c.get("/api/auth/config").json() == {"auth_mode": "passcode", "email_available": True}


def test_readonly_session_polling_does_not_extend_idle_expiry(tmp_path, monkeypatch):
    with build(tmp_path, accounts_session_idle_hours=1) as c:
        sign_in(c, tmp_path, "poll@example.com")
        raw = c.cookies.get("st_session")
        settings = c.app.state.auth.settings
        with c.app.state.session_factory() as db:
            started = accounts.aware(db.get(AuthSession, accounts.hash_secret(raw)).last_seen_at)
        for minutes in (10, 30, 50, 59):
            monkeypatch.setattr(accounts, "now", lambda minutes=minutes: started + timedelta(minutes=minutes))
            with c.app.state.session_factory() as db:
                assert accounts.resolve_session(db, settings, raw, touch=False) is not None
                seen = accounts.aware(db.get(AuthSession, accounts.hash_secret(raw)).last_seen_at)
                assert seen == started and not db.dirty
        monkeypatch.setattr(accounts, "now", lambda: started + timedelta(minutes=61))
        with c.app.state.session_factory() as db:
            assert accounts.resolve_session(db, settings, raw, touch=False) is None


def test_user_action_refreshes_idle_expiry_but_following_polls_do_not(tmp_path, monkeypatch):
    with build(tmp_path, accounts_session_idle_hours=1) as c:
        sign_in(c, tmp_path, "active@example.com")
        raw = c.cookies.get("st_session")
        settings = c.app.state.auth.settings
        with c.app.state.session_factory() as db:
            started = accounts.aware(db.get(AuthSession, accounts.hash_secret(raw)).last_seen_at)
        action_at = started + timedelta(minutes=50)
        monkeypatch.setattr(accounts, "now", lambda: action_at)
        with c.app.state.session_factory() as db:
            assert accounts.resolve_session(db, settings, raw, touch=True) is not None
        monkeypatch.setattr(accounts, "now", lambda: started + timedelta(minutes=109))
        with c.app.state.session_factory() as db:
            assert accounts.resolve_session(db, settings, raw, touch=False) is not None
            assert accounts.aware(db.get(AuthSession, accounts.hash_secret(raw)).last_seen_at) == action_at
        monkeypatch.setattr(accounts, "now", lambda: started + timedelta(minutes=111))
        with c.app.state.session_factory() as db:
            assert accounts.resolve_session(db, settings, raw, touch=False) is None
