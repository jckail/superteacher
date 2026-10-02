"""Session cookie integrity/lifetime/flags and the login throttle (incl. X-Forwarded-For behaviour)."""

import base64
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from superteacher import auth
from superteacher.config import Settings
from tests.sec_util import PW, H, behind_proxy, build, login

BROWSER = {**H, "Origin": "http://testserver", "X-Forwarded-Proto": "http"}


@pytest.fixture
def c():
    with build() as client:
        yield client


def token_of(client) -> str:
    assert login(client).status_code == 200
    return client.cookies.get(auth.COOKIE)


def probe(client, token: str | None) -> int:
    client.cookies.clear()
    if token is not None:
        client.cookies.set(auth.COOKIE, token)
    return client.get("/api/overview").status_code


# ── cookie integrity ────────────────────────────────────────────────────
def test_valid_token_is_accepted_baseline(c):
    assert probe(c, token_of(c)) == 200


def test_tampered_tokens_rejected(c):
    tok = token_of(c)
    payload, ts, sig = tok.split(".")
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    forged_payload = base64.urlsafe_b64encode(b'{"v":2,"admin":true}').decode().rstrip("=")
    cases = {
        "flipped signature": f"{payload}.{ts}.{flipped}",
        "swapped payload": f"{forged_payload}.{ts}.{sig}",
        "swapped timestamp": f"{payload}.AAAAAA.{sig}",
        "no signature": f"{payload}.{ts}",
        "truncated": tok[: len(tok) // 2],
        "truncated by one": tok[:-1],
        "extended": tok + "A",
        "empty": "",
        "dots only": "..",
        "garbage": "not-a-token",
        "null byte": tok + "\x00",
        "huge": "A" * 100_000,
        "unsigned json": '{"v":1}',
        "other secret": None,
    }
    other = build(session_secret="x" * 32)
    with other:
        cases["other secret"] = token_of(other)
    for name, bad in cases.items():
        assert probe(c, bad) == 401, name
    assert c.get("/api/auth/me").status_code == 401


def test_token_survives_only_with_matching_secret_and_password():
    with build() as a, build(session_secret="z" * 32) as other_secret, build(auth_password="new passcode") as new_pw:
        tok = token_of(a)
        assert probe(other_secret, tok) == 401  # different SESSION_SECRET
        assert probe(new_pw, tok) == 401  # replay after the passcode was changed


def test_expired_token_rejected(c, monkeypatch):
    tok = token_of(c)
    ttl = c.app.state.auth.ttl
    assert probe(c, tok) == 200
    real = TimestampSigner.get_timestamp
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: real(self) + ttl + 5)  # clock moves on
    assert probe(c, tok) == 401
    assert c.get("/api/auth/me").status_code == 401


def test_ttl_is_bounded_by_config():
    with build(session_ttl_hours=1) as c:
        assert c.app.state.auth.ttl == 3600
        assert "max-age=3600" in login(c).headers["set-cookie"].lower()


# ── cookie flags ────────────────────────────────────────────────────────
def test_cookie_flags_http(c):
    sc = login(c).headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc and "path=/" in sc
    assert "secure" not in sc.split(";")[1:] and "; secure" not in sc  # plain http dev: not Secure
    assert "domain=" not in sc  # host-only cookie, not shared with sibling subdomains


def test_cookie_secure_when_request_is_https(c):
    with TestClient(c.app, base_url="https://testserver") as secure_client:
        assert "; secure" in login(secure_client).headers["set-cookie"].lower()


@pytest.mark.parametrize("trusted", [False, True])
def test_cookie_secure_uses_only_trusted_proxy_scheme(c, trusted):
    with behind_proxy(c, trusted=trusted) as proxied:
        response = login(proxied, **{"X-Forwarded-Proto": "https"})
        assert response.status_code == 200
        assert ("; secure" in response.headers["set-cookie"].lower()) is trusted


def test_spoofed_forwarded_proto_does_not_force_secure_cookie(c):
    for value in ("https", "https, http"):
        response = login(c, **{"X-Forwarded-Proto": value})
        assert response.status_code == 200
        assert "; secure" not in response.headers["set-cookie"].lower()


def test_cookie_secure_can_be_forced():
    with build(cookie_secure=True) as c:
        assert "; secure" in login(c).headers["set-cookie"].lower()


def test_failed_login_sets_no_cookie(c):
    r = login(c, "wrong")
    assert r.status_code == 401 and "set-cookie" not in r.headers
    assert PW not in r.text


def test_login_response_and_errors_do_not_reveal_passcode_or_secret(c):
    r = login(c)
    assert PW not in r.text and "s" * 32 not in r.text
    assert set(r.json()) == {"authenticated", "auth_required"}


# ── logout ──────────────────────────────────────────────────────────────
def test_logout_clears_the_browser_cookie(c):
    login(c)
    r = c.post("/api/auth/logout", headers=H)
    assert r.status_code == 200
    sc = r.headers["set-cookie"].lower()
    assert "max-age=0" in sc or "expires=" in sc
    assert c.get("/api/overview").status_code == 401


@pytest.mark.xfail(
    reason="KNOWN LIMITATION F-06: sessions are stateless signed cookies, so a copied cookie stays valid until expiry "
    "or a passcode change. Remove the xfail if a server-side revocation list is added.",
    strict=False,
)
def test_copied_cookie_is_dead_after_logout(c):
    tok = token_of(c)
    c.post("/api/auth/logout", headers=H)
    assert probe(c, tok) == 401


# ── secret persistence ──────────────────────────────────────────────────
def test_generated_session_secret_is_private_and_stable(tmp_path: Path):
    s = Settings(auth_password=PW, session_secret=None)
    a = auth.AuthState(s, tmp_path)
    f = tmp_path / ".session_secret"
    assert f.is_file() and stat.S_IMODE(f.stat().st_mode) == 0o600
    assert len(f.read_text().strip()) >= 32
    b = auth.AuthState(s, tmp_path)
    assert b.valid(a.issue())  # survives a restart
    assert not auth.AuthState(Settings(auth_password="other", session_secret=None), tmp_path).valid(a.issue())


def test_no_secret_dir_gives_an_ephemeral_but_random_secret():
    s = Settings(auth_password=PW, session_secret=None)
    a, b = auth.AuthState(s, None), auth.AuthState(s, None)
    assert not b.valid(a.issue())


# ── throttle ────────────────────────────────────────────────────────────
def attempt(client, ip: str, pw: str = "wrong"):
    return client.post("/api/auth/login", json={"password": pw}, headers={**BROWSER, "X-Forwarded-For": ip})


def test_lockout_then_retry_after_header(c):
    for _ in range(auth.MAX_FREE_ATTEMPTS):
        assert login(c, "nope").status_code == 401
    r = login(c, "nope")
    assert r.status_code == 429 and 0 < int(r.headers["retry-after"]) <= auth.LOCK_BASE_SECONDS + 1
    assert login(c).status_code == 429  # the right passcode does not bypass a lockout
    assert c.get("/api/auth/me").status_code == 401


def test_lockout_expires_and_backs_off_exponentially(c, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    for _ in range(auth.MAX_FREE_ATTEMPTS):
        login(c, "nope")
    first = int(login(c).headers["retry-after"])
    now[0] += first + 1
    assert login(c, "nope").status_code == 401  # one more failure is allowed after the wait...
    second = int(login(c).headers["retry-after"])
    assert second >= 2 * auth.LOCK_BASE_SECONDS - 1  # ...and the next lock is twice as long
    now[0] += 10 * 3600
    assert login(c).status_code == 200  # all locks eventually expire; cap is LOCK_MAX_SECONDS
    assert second <= auth.LOCK_MAX_SECONDS + 1


def test_lock_wait_is_capped():
    st = auth.AuthState(Settings(auth_password=PW, session_secret="s" * 32))
    for _ in range(auth.MAX_FREE_ATTEMPTS + 40):
        st.record("1.2.3.4", False)
    assert st.retry_after("1.2.3.4") <= auth.LOCK_MAX_SECONDS + 1


def test_successful_login_resets_that_clients_counter(c):
    for _ in range(auth.MAX_FREE_ATTEMPTS - 1):
        login(c, "nope")
    assert login(c).status_code == 200
    for _ in range(auth.MAX_FREE_ATTEMPTS - 1):
        assert login(c, "nope").status_code == 401  # a fresh allowance, not 1 left


def test_malformed_login_bodies_are_not_oracles_and_never_500():
    with build(raise_server_exceptions=False) as c:
        for body in ('{"password": 1}', '{"password": null}', "{}", "[]", "not json", '{"password": ["a"]}'):
            r = c.post("/api/auth/login", content=body, headers={**H, "content-type": "application/json"})
            assert r.status_code in (400, 422), body


def test_lone_surrogate_passcode_is_rejected_without_a_500():
    with build(raise_server_exceptions=False) as c:
        r = c.post(
            "/api/auth/login", content='{"password":"\\ud800"}', headers={**H, "content-type": "application/json"}
        )
        assert r.status_code == 422
        assert "\\ud800" not in r.text


def test_huge_passcode_is_handled_in_constant_work():
    with build() as c:
        response = login(c, "A" * 1_000_000)
        assert response.status_code == 422
        assert len(response.content) < 1024


@pytest.mark.parametrize("trusted", [False, True])
def test_xff_untrusted_vs_trusted_per_client_keys(trusted):
    with build() as base, behind_proxy(base, trusted) as p:
        for _ in range(auth.MAX_FREE_ATTEMPTS):
            attempt(p, "203.0.113.7")
        assert attempt(p, "203.0.113.7", PW).status_code == 429
        other = attempt(p, "198.51.100.9", PW).status_code
        # trusted proxy headers: a different client is unaffected. Untrusted: X-Forwarded-For is ignored, so
        # everyone behind the proxy shares one bucket (this is why the image sets FORWARDED_ALLOW_IPS).
        assert other == (200 if trusted else 429)


def test_rotating_xff_cannot_bypass_when_headers_are_ignored():
    with build() as base, behind_proxy(base, trusted=False) as p:
        codes = [attempt(p, f"10.0.0.{i}").status_code for i in range(auth.MAX_FREE_ATTEMPTS + 5)]
    assert codes.count(401) == auth.MAX_FREE_ATTEMPTS and set(codes[auth.MAX_FREE_ATTEMPTS :]) == {429}


def test_rotating_xff_is_bounded_by_the_global_limiter_when_headers_are_trusted():
    """With FORWARDED_ALLOW_IPS=* an attacker picks their own 'client address', defeating the per-client lock
    (accepted risk F-05). The global limiter must still cap total guesses."""
    with build() as base, behind_proxy(base, trusted=True) as p:
        codes = [attempt(p, f"10.1.{i // 250}.{i % 250}").status_code for i in range(auth.GLOBAL_MAX_ATTEMPTS + 30)]
        assert codes.count(401) == auth.GLOBAL_MAX_ATTEMPTS
        assert set(codes[auth.GLOBAL_MAX_ATTEMPTS :]) == {429}
        assert attempt(p, "192.0.2.55", PW).status_code == 429  # even a brand-new client / right passcode waits
        assert len(base.app.state.auth._fails) <= auth.GLOBAL_MAX_ATTEMPTS + 1  # no unbounded memory growth


def test_lockout_check_does_not_consume_attempts(c):
    for _ in range(auth.MAX_FREE_ATTEMPTS):
        login(c, "nope")
    st = c.app.state.auth
    before = dict(st._fails)
    for _ in range(20):
        assert login(c, "nope").status_code == 429
    assert st._fails == before  # hammering a locked client doesn't extend its own lock (or fill memory)
