import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from superteacher import auth
from superteacher import db as database
from superteacher.config import Settings
from superteacher.main import create_app

PW = "correct horse"
H = {"X-Requested-With": "test"}


def make(**kw) -> TestClient:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sf = sessionmaker(bind=eng, expire_on_commit=False)
    s = Settings(
        auth_password=PW, auth_disabled=False, session_secret="s" * 32, cors_origins=["http://localhost:4000"], **kw
    )
    app = create_app(session_factory=sf, engine=eng, seed=False, settings=s)

    def override():
        with sf() as db:
            yield db

    app.dependency_overrides[database.get_db] = override
    return TestClient(app, base_url="http://testserver")


@pytest.fixture
def c():
    with make() as client:
        yield client


def login(c, pw=PW):
    return c.post("/api/auth/login", json={"password": pw}, headers=H)


def test_refuses_to_start_without_password():
    with pytest.raises(RuntimeError, match="AUTH_PASSWORD"):
        create_app(settings=Settings(auth_password=None, auth_disabled=False))


def test_open_only_when_explicitly_disabled():
    app = create_app(settings=Settings(auth_disabled=True))
    assert app.state.auth.disabled


def test_public_endpoints_and_protected(c):
    assert c.get("/api/health").json()["status"] == "healthy"
    assert c.get("/api/version").status_code == 200
    for path in ("/api/overview", "/api/students", "/api/courses"):
        assert c.get(path).status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_login_logout_cycle(c):
    assert login(c, "wrong").status_code == 401
    r = login(c)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert c.get("/api/auth/me").json()["authenticated"] is True
    assert c.get("/api/overview").status_code == 200
    assert c.post("/api/auth/logout", headers=H).status_code == 200
    assert c.get("/api/overview").status_code == 401


def test_tampered_or_foreign_cookie_rejected(c):
    c.cookies.set(auth.COOKIE, "garbage")
    assert c.get("/api/overview").status_code == 401
    with make() as other:
        other.app.state.auth.serializer.secret_keys = [b"different"]
        login(other)
        c.cookies.set(auth.COOKIE, other.cookies.get(auth.COOKIE))
    assert c.get("/api/overview").status_code == 401


def test_expired_session(c, monkeypatch):
    login(c)
    c.app.state.auth.ttl = -1
    assert c.get("/api/overview").status_code == 401


def test_csrf_header_required_for_writes(c):
    login(c)
    r = c.post("/api/courses", json={"name": "X"})
    assert r.status_code == 403
    assert c.post("/api/courses", json={"name": "X"}, headers=H).status_code != 403
    assert c.post("/api/auth/login", json={"password": PW}).status_code == 403  # login needs it too


def test_cross_origin_rejected(c):
    login(c)
    assert c.get("/api/overview", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/overview", headers={"Origin": "http://localhost:4000"}).status_code == 200
    assert c.get("/api/overview", headers={"Origin": "http://testserver"}).status_code == 200


@pytest.mark.parametrize(
    "origin",
    ["https://testserver", "ftp://testserver", "http://user@testserver", "http://testserver/path", "null"],
)
def test_origin_requires_exact_scheme_and_valid_browser_origin(c, origin):
    login(c)
    assert c.get("/api/overview", headers={"Origin": origin}).status_code == 403


def test_lockout_expires_after_inactivity(c, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    st = c.app.state.auth
    for _ in range(auth.GLOBAL_MAX_ATTEMPTS):
        st.record("attacker", False)
    assert st.retry_after("another-client") > 0
    now[0] += auth.FAILURE_RESET_SECONDS
    assert st.retry_after("attacker") == 0
    assert st.retry_after("another-client") == 0
    st.record("attacker", False)
    assert st._fails["attacker"][0] == 1


def test_throttle_caps_exponential_and_memory(c, monkeypatch):
    monkeypatch.setattr(auth.time, "monotonic", lambda: 100.0)
    st = c.app.state.auth
    st._fails["attacker"] = (100_000, 100.0)
    assert st.retry_after("attacker") <= auth.LOCK_MAX_SECONDS + 1
    for i in range(10_100):
        st.record(str(i), False)
    assert len(st._fails) <= 10_000
    assert "*" in st._fails


def test_login_payload_bounded(c):
    assert login(c, "x" * 1025).status_code == 422


def test_lockout_after_repeated_failures(c):
    for _ in range(auth.MAX_FREE_ATTEMPTS):
        assert login(c, "nope").status_code == 401
    r = login(c, "nope")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert login(c).status_code == 429  # even the right passcode waits out the lockout


def test_websocket_requires_cookie_and_origin(c):
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/api/chat/ws"):
        pass
    login(c)
    with (
        pytest.raises(WebSocketDisconnect),
        c.websocket_connect("/api/chat/ws", headers={"origin": "https://evil.example"}),
    ):
        pass
    with c.websocket_connect("/api/chat/ws", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"type": "reset"})


def test_security_headers_and_cors(c):
    r = c.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"]
    pre = c.options("/api/overview", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers


def test_docs_hidden_by_default(c):
    assert "swagger" not in c.get("/api/docs").text.lower()
    assert "openapi" not in c.get("/api/openapi.json").text[:200].lower()


def test_disabled_mode_open():
    s = Settings(auth_disabled=True)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sf = sessionmaker(bind=eng)
    app = create_app(session_factory=sf, engine=eng, seed=False, settings=s)
    app.dependency_overrides[database.get_db] = lambda: iter([sf()])
    with TestClient(app) as cl:
        assert cl.get("/api/auth/me").json() == {"authenticated": True, "auth_required": False}


def _behind_tls_proxy(client: TestClient, trusted: bool) -> TestClient:
    """The same app as a TLS-terminating proxy (Cloud Run) presents it: browsers speak https, the app sees http."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app = ProxyHeadersMiddleware(client.app, trusted_hosts="*") if trusted else client.app
    return TestClient(app, base_url="http://testserver")


BROWSER = {**H, "Origin": "https://testserver", "X-Forwarded-Proto": "https"}


def test_https_browser_origin_accepted_when_proxy_headers_are_trusted():
    # The trusted platform proxy converts the scope to the browser scheme.
    with make() as base, _behind_tls_proxy(base, trusted=True) as proxied:
        assert proxied.post("/api/auth/login", json={"password": PW}, headers=BROWSER).status_code == 200


def test_websocket_with_https_origin_and_session_cookie():
    with make() as base, _behind_tls_proxy(base, trusted=True) as proxied:
        r = proxied.post("/api/auth/login", json={"password": PW}, headers=BROWSER)
        cookie = f"{auth.COOKIE}={r.cookies[auth.COOKIE]}"
        headers = {"Origin": "https://testserver", "X-Forwarded-Proto": "https", "Cookie": cookie}
        with proxied.websocket_connect("/api/chat/ws", headers=headers) as ws:
            ws.send_json({"content": "hi"})
            assert ws.receive_json()["type"] in {"delta", "error", "done"}


def test_cross_site_origin_still_rejected():
    with make() as base, _behind_tls_proxy(base, trusted=True) as proxied:
        evil = {**BROWSER, "Origin": "https://evil.example"}
        assert proxied.post("/api/auth/login", json={"password": PW}, headers=evil).status_code == 403


def _attempt(client: TestClient, ip: str, pw: str):
    return client.post("/api/auth/login", json={"password": pw}, headers={**H, "X-Forwarded-For": ip})


def test_lockout_is_per_client_when_proxy_headers_are_trusted():
    # Behind Cloud Run every request comes from the platform's front end. If uvicorn doesn't trust X-Forwarded-For
    # (FORWARDED_ALLOW_IPS), all users share one address and five typos from anyone lock everyone out.
    with make() as base, _behind_tls_proxy(base, trusted=True) as proxied:
        for _ in range(auth.MAX_FREE_ATTEMPTS + 1):
            _attempt(proxied, "203.0.113.7", "wrong")
        assert _attempt(proxied, "203.0.113.7", PW).status_code == 429  # the noisy client is locked out...
        assert _attempt(proxied, "198.51.100.9", PW).status_code == 200  # ...a different client is not


def test_lockout_is_shared_when_proxy_headers_are_not_trusted():
    with make() as base, _behind_tls_proxy(base, trusted=False) as proxied:
        for _ in range(auth.MAX_FREE_ATTEMPTS + 1):
            _attempt(proxied, "203.0.113.7", "wrong")
        assert _attempt(proxied, "198.51.100.9", PW).status_code == 429  # why the image must set FORWARDED_ALLOW_IPS


def test_untrusted_forwarded_proto_does_not_bypass_origin_scheme():
    with make() as base, _behind_tls_proxy(base, trusted=False) as proxied:
        assert proxied.post("/api/auth/login", json={"password": PW}, headers=BROWSER).status_code == 403
