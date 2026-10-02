"""Login-token lifecycle: single use, expiry, tampering, replay, wrong email, scanner prefetch."""

from datetime import timedelta

from sqlalchemy import select, update

from superteacher import accounts
from superteacher.models import LoginToken, User
from tests.acct_util import H, build, outbox, request_link, sign_in, token_from, verify


def test_happy_path_creates_user_and_session(tmp_path):
    with build(tmp_path) as c:
        body = sign_in(c, tmp_path, "Teacher@Example.com")
        assert body["authenticated"] and body["email"] == "teacher@example.com" and body["new_user"] is True
        me = c.get("/api/auth/me").json()
        assert me["email"] == "teacher@example.com" and me["auth_mode"] == "accounts"
        assert c.get("/api/overview").status_code == 200


def test_token_is_single_use_and_replay_fails(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        assert verify(c, tok).status_code == 200
        c.cookies.clear()
        r = verify(c, tok)  # replay
        assert r.status_code == 400 and "invalid or has expired" in r.json()["detail"]
        assert c.get("/api/auth/me").status_code == 401


def test_token_is_not_consumed_by_get(tmp_path):
    """Mail scanners prefetch links with GET; the link is a SPA page and only POST /verify spends the token."""
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        for path in ("/auth/verify", f"/api/auth/verify?token={tok}"):
            c.get(path)
        assert verify(c, tok).status_code == 200


def test_link_puts_token_in_the_fragment_never_the_query(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        msg = outbox(tmp_path)[-1]
        assert "http://testserver/auth/verify#token=" in msg["text"]
        assert "?token" not in msg["text"] and "?token" not in msg["html"]
        assert "ignore it" in msg["text"] and "ignore it" in msg["html"]
        assert "<img" not in msg["html"]  # no tracking pixel


def test_expired_token_rejected(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        with c.app.state.session_factory() as db:
            db.execute(update(LoginToken).values(expires_at=accounts.now() - timedelta(seconds=1)))
            db.commit()
        assert verify(c, tok).status_code == 400
        with c.app.state.session_factory() as db:
            assert db.scalar(select(User)) is None  # nothing was created


def test_token_ttl_is_fifteen_minutes(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        with c.app.state.session_factory() as db:
            t = db.scalar(select(LoginToken))
            ttl = accounts.aware(t.expires_at) - accounts.aware(t.created_at)
            assert timedelta(minutes=14, seconds=55) < ttl <= timedelta(minutes=15)


def test_tampered_or_guessed_tokens_rejected(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        flipped = tok[:-1] + ("A" if tok[-1] != "A" else "B")
        for bad in (flipped, tok + "x", tok[:-4], tok.upper(), "A" * 43, "x" * 16):
            assert verify(c, bad).status_code == 400, bad
        assert verify(c, tok).status_code == 200  # the real one still works after the failed guesses


def test_malformed_verify_bodies(tmp_path):
    with build(tmp_path) as c:
        for body in ({}, {"token": ""}, {"token": 5}, {"token": "x" * 500}, {"token": None}, []):
            r = c.post("/api/auth/verify", json=body, headers=H)
            assert r.status_code in (400, 422), body


def test_token_for_one_email_never_signs_in_another(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "alice@example.com")
        request_link(c, "bob@example.com")
        a, b = [token_from(m) for m in outbox(tmp_path)]
        assert verify(c, a).json()["email"] == "alice@example.com"
        c.cookies.clear()
        assert verify(c, b).json()["email"] == "bob@example.com"


def test_only_hashes_are_stored(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        raw_cookie = c.cookies.get("st_session")
        with c.app.state.session_factory() as db:
            stored = db.scalar(select(LoginToken))
            assert stored.token_hash == accounts.hash_secret(tok) and tok not in stored.token_hash
            from sqlalchemy import text

            dump = " ".join(
                str(r) for t in ("login_tokens", "sessions") for r in db.execute(text(f"select * from {t}"))
            )
            assert tok not in dump and raw_cookie not in dump
            assert stored.ip_hash and "testclient" not in stored.ip_hash


def test_verify_requires_csrf_header_and_same_origin(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "a@example.com")
        tok = token_from(outbox(tmp_path)[-1])
        assert c.post("/api/auth/verify", json={"token": tok}).status_code == 403
        assert verify(c, tok, Origin="https://evil.example").status_code == 403
        assert c.post("/api/auth/request-link", json={"email": "a@example.com"}).status_code == 403
        assert request_link(c, "a@example.com", Origin="https://evil.example").status_code == 403
        assert verify(c, tok, Origin="http://testserver").status_code == 200  # nothing above burned it


def test_email_normalisation_and_shape():
    n = accounts.normalize_email
    assert n("  Ada@Example.COM ") == "ada@example.com"
    assert n("ａｄａ@example.com") == "ada@example.com"  # NFKC folds full-width forms
    assert n("a+tag@sub.example.co.uk") == "a+tag@sub.example.co.uk"
    for bad in (
        "",
        "no-at",
        "a@b",
        "a@@b.co",
        "a b@c.co",
        "a@b..co",
        ".a@b.co",
        "a.@b.co",
        "a@-b.co",
        "a@b.c1",
        "a@1.2.3.4",
        "a\n@b.co",
        "a@b.co\r\nBcc: x@y.co",
        "x" * 65 + "@b.co",
        "a@" + "b" * 64 + ".co",
        None,
        5,
    ):
        assert n(bad) is None, bad
