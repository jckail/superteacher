"""Every route is authenticated unless it is on an explicit allowlist; CSRF / Origin checks hold for every verb."""

import pytest
from starlette.websockets import WebSocketDisconnect

from superteacher import auth
from tests.sec_util import H, build, flatten_routes, login, seed_class

# The ONLY routes reachable without a session. Adding a route here is a security decision: justify it in the PR.
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/version"),
    # Readiness probe for the platform: returns only a fixed status body (no details, no data); see observability.py.
    ("GET", "/api/ready"),
    ("POST", "/api/auth/login"),
    # Accounts mode sign-in (404 in passcode mode). Public by necessity: they are how a session starts. Each answers
    # without a session only with generic bodies, is CSRF/Origin-checked and rate limited; see tests/test_accounts_*.
    ("GET", "/api/auth/config"),
    ("POST", "/api/auth/request-link"),
    ("POST", "/api/auth/verify"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
}


@pytest.fixture(scope="module")
def app_client():
    with build() as c:
        yield c


def _routes(app):
    return flatten_routes(app.routes)


def _fill(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "x", path)


def test_every_route_lives_under_api_or_is_known(app_client):
    for kind, path in _routes(app_client.app):
        assert path.startswith("/api") or path in {"/{path:path}", "/assets"}, f"unexpected top-level route {path}"
        assert kind != "Route", f"plain (non-FastAPI) route {path} bypasses router-level dependencies"


def test_public_allowlist_has_no_stale_entries(app_client):
    present = set(_routes(app_client.app))
    assert present >= PUBLIC, f"allowlist names routes that no longer exist: {PUBLIC - present}"


def test_route_inventory_is_not_trivially_empty(app_client):
    assert len(list(_routes(app_client.app))) > 25


def test_every_non_public_api_route_requires_a_session(app_client):
    """Fails when someone adds an /api route without the auth dependency."""
    c = app_client
    offenders, checked = [], 0
    for method, path in _routes(c.app):
        if method == "WS" or (method, path) in PUBLIC or not path.startswith("/api"):
            continue
        checked += 1
        # CSRF header + same-origin Origin present, cookie absent: the only thing missing is the session.
        r = c.request(method, _fill(path), headers={**H, "Origin": "http://testserver"}, json={})
        if r.status_code != 401:
            offenders.append((method, path, r.status_code))
    assert checked > 20
    assert offenders == [], f"routes reachable without a session: {offenders}"


def test_every_authenticated_route_resolves_the_current_user(app_client):
    """Tenancy rests on one dependency. Swap it for a spy and require every non-public route to call it."""
    from fastapi.requests import HTTPConnection

    from superteacher.accounts import CurrentUser

    app = app_client.app
    seen: set[str] = set()

    async def spy(conn: HTTPConnection):
        seen.add(conn.scope["path"])
        return CurrentUser("probe0000000", "probe@example.invalid")

    app.dependency_overrides[auth.current_user] = spy
    try:
        missing = []
        for method, path in _routes(app):
            if method in ("WS", "MOUNT") or (method, path) in PUBLIC or not path.startswith("/api"):
                continue
            if (method, path) == ("GET", "/api/metrics"):
                continue  # operator endpoint: METRICS_TOKEN bearer, no tenant data; 401 for sessions in accounts mode
            concrete = _fill(path)
            seen.discard(concrete)
            app_client.request(method, concrete, headers={**H, "Origin": "http://testserver"}, json={})
            if concrete not in seen:
                missing.append((method, path))
        assert missing == [], f"authenticated routes that never resolve current_user: {missing}"
        sockets = [p for m, p in _routes(app) if m == "WS"]
        for path in sockets:
            seen.discard(path)
            with app_client.websocket_connect(path) as ws:
                ws.send_json({"type": "reset"})
            assert path in seen, path
    finally:
        app.dependency_overrides.pop(auth.current_user, None)


def test_non_public_routes_also_reject_a_forged_cookie(app_client):
    c = app_client
    c.cookies.set(auth.COOKIE, "forged.token.value")
    try:
        for method, path in _routes(c.app):
            if method == "WS" or (method, path) in PUBLIC or not path.startswith("/api"):
                continue
            assert c.request(method, _fill(path), headers=H, json={}).status_code == 401, (method, path)
    finally:
        c.cookies.clear()


def test_every_websocket_route_requires_a_session(app_client):
    sockets = [p for m, p in _routes(app_client.app) if m == "WS"]
    assert "/api/chat/ws" in sockets
    for path in sockets:
        with pytest.raises(WebSocketDisconnect) as e, app_client.websocket_connect(path):
            pass
        assert e.value.code == 1008


def test_public_routes_leak_nothing_sensitive(app_client):
    assert set(app_client.get("/api/health").json()) == {"status", "database", "ai"}
    assert app_client.get("/api/version").json().keys() == {"version", "git_commit"}
    assert app_client.get("/api/auth/me").status_code == 401


def test_unauthenticated_unknown_method_does_not_reach_handlers(app_client):
    for m in ("PUT", "DELETE", "PATCH"):
        assert app_client.request(m, "/api/overview", headers=H).status_code in (401, 405)


# ── CSRF / Origin matrix ────────────────────────────────────────────────
# Only http(s) origins are ever accepted: a non-web scheme with the right host must be refused (F-11, fixed).
SCHEME_GAP = "ftp://testserver"
BAD_ORIGINS = [
    "https://evil.com",
    "http://evil.com",
    "null",
    "",
    "file://",
    "https://testserver.evil.com",
    "http://testserver.evil.com",
    "https://evil.com/testserver",
    "https://evil.com#testserver",
    "https://testserver@evil.com",
    "https://evil.com@testserver",
    "http://testserver:8080",  # port confusion
    "http://testserver:80@evil.com",
    "http://testserver.",
    "http://xtestserver",
    "http://localhost:4000.evil.com",
    "http://localhost:4000@evil.com",
    "http://localhost:4001",
    "https://localhost:4000",  # a configured origin is matched exactly, scheme included
    "http://testserver\\@evil.com",
]
GOOD_ORIGINS = [
    "http://testserver",
    "http://testserver/",
    "HTTP://TESTSERVER",
    "http://localhost:4000",
    # HTTPS origins use an HTTPS request scope; trusted TLS proxy conversion is tested separately.
    "https://testserver",
]


@pytest.fixture
def authed():
    with build() as c:
        assert login(c).status_code == 200
        ids = seed_class(c)
        yield c, ids


def _verbs(ids):
    s, st = ids["section"], ids["students"][0]
    return [
        ("POST", "/api/courses", {"name": "Other"}),
        ("POST", f"/api/sections/{s}/assessments", {"title": "Quiz"}),
        ("PUT", f"/api/sections/{s}/attendance", {"marks": []}),
        ("PATCH", f"/api/students/{st}", {"grade_level": 10}),
        ("DELETE", f"/api/students/{st}", None),
    ]


def test_state_changing_requests_need_the_csrf_header(authed):
    c, ids = authed
    for method, path, body in _verbs(ids):
        assert c.request(method, path, json=body).status_code == 403, (method, path)  # no header at all
        # A "simple" cross-site form post can't set custom headers; a wrong header *name* must not satisfy it.
        assert c.request(method, path, json=body, headers={"X-Requested": "1"}).status_code == 403


@pytest.mark.parametrize("origin", [*BAD_ORIGINS, SCHEME_GAP])
def test_hostile_origin_blocked_for_every_verb(authed, origin):
    c, ids = authed
    for method, path, body in _verbs(ids):
        r = c.request(method, path, json=body, headers={**H, "Origin": origin})
        assert r.status_code == 403, (method, origin)
    assert c.get("/api/overview", headers={"Origin": origin}).status_code == 403
    assert c.post("/api/auth/login", json={"password": "x"}, headers={**H, "Origin": origin}).status_code == 403
    assert c.post("/api/auth/logout", headers={**H, "Origin": origin}).status_code == 403
    # The blocked requests must not have changed anything.
    assert len(c.get("/api/students").json()) == 1


@pytest.mark.parametrize("origin", GOOD_ORIGINS)
def test_legitimate_origins_work(authed, origin):
    c, _ = authed
    base = "https://testserver" if origin == "https://testserver" else "http://testserver"
    assert c.get(f"{base}/api/overview", headers={"Origin": origin}).status_code == 200
    r = c.post(f"{base}/api/courses", json={"name": f"ok-{abs(hash(origin))}"}, headers={**H, "Origin": origin})
    assert r.status_code == 201


@pytest.mark.parametrize("origin", [*BAD_ORIGINS, SCHEME_GAP])
def test_websocket_handshake_blocks_hostile_origin(authed, origin):
    c, _ = authed
    with pytest.raises(WebSocketDisconnect) as e, c.websocket_connect("/api/chat/ws", headers={"origin": origin}):
        pass
    assert e.value.code == 1008


@pytest.mark.parametrize("origin", GOOD_ORIGINS)
def test_websocket_handshake_allows_own_origin(authed, origin):
    c, _ = authed
    scheme = "wss" if origin == "https://testserver" else "ws"
    with c.websocket_connect(f"{scheme}://testserver/api/chat/ws", headers={"origin": origin}) as ws:
        ws.send_json({"type": "reset"})


@pytest.mark.parametrize("scheme,origin", [("http", "https://testserver"), ("https", "http://testserver")])
def test_same_host_with_mismatched_scheme_is_rejected(authed, scheme, origin):
    c, _ = authed
    assert c.get(f"{scheme}://testserver/api/overview", headers={"Origin": origin}).status_code == 403
    assert (
        c.post(
            f"{scheme}://testserver/api/courses", json={"name": "Blocked"}, headers={**H, "Origin": origin}
        ).status_code
        == 403
    )
    ws_scheme = "wss" if scheme == "https" else "ws"
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        c.websocket_connect(f"{ws_scheme}://testserver/api/chat/ws", headers={"origin": origin}),
    ):
        pass
    assert exc.value.code == 1008


def test_websocket_without_origin_still_needs_cookie(authed):
    """Non-browser clients send no Origin; they are still held to the session cookie."""
    c, _ = authed
    saved = dict(c.cookies)
    c.cookies.clear()
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/api/chat/ws"):
        pass
    c.cookies.update(saved)
    with c.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"type": "reset"})


def test_cors_preflight_only_for_configured_origins(authed):
    c, _ = authed
    for origin in ("https://evil.com", "null", "https://testserver.evil.com"):
        r = c.options("/api/courses", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in r.headers
        # Simple responses to a hostile origin must not be readable cross-site either.
        assert "access-control-allow-origin" not in c.get("/api/overview", headers={"Origin": origin}).headers
    ok = c.options(
        "/api/courses",
        headers={
            "Origin": "http://localhost:4000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-requested-with",
        },
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:4000"
    # a wildcard with credentials would be a hole
    assert ok.headers["access-control-allow-origin"] != "*"


def test_roster_cursor_preflight_preserves_origin_and_session_guards():
    with build() as c:
        headers = {
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-requested-with,x-roster-cursor",
        }
        allowed = c.options("/api/students/page", headers={**headers, "Origin": "http://localhost:4000"})
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:4000"
        assert allowed.headers["access-control-allow-credentials"] == "true"
        assert "x-roster-cursor" in allowed.headers["access-control-allow-headers"].lower()
        denied = c.options("/api/students/page", headers={**headers, "Origin": "https://evil.com"})
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers
        # A permitted preflight is not authorization to read the roster.
        protected = c.get(
            "/api/students/page",
            headers={"Origin": "http://localhost:4000", "X-Roster-Cursor": "synthetic", **H},
        )
        assert protected.status_code == 401
