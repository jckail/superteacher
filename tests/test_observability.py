import asyncio
import json
import logging
import random
import string

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from superteacher import ai, observability, reports
from superteacher import db as database
from superteacher.config import Settings, get_settings
from superteacher.main import create_app
from superteacher.models import Student
from tests.ai_fakes import FakeAI, api_error, end_turn

OBS = observability
REG = observability.REGISTRY
PW = "correct horse battery"
H = {"X-Requested-With": "test"}


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(observability.JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))

    def events(self, name=None):
        out = [json.loads(line) for line in self.lines]
        return [e for e in out if name is None or e.get("event") == name]


@pytest.fixture
def logs():
    h = Capture()
    lg = logging.getLogger()
    lg.addHandler(h)
    old = lg.level
    lg.setLevel(logging.DEBUG)
    yield h
    lg.removeHandler(h)
    lg.setLevel(old)


def make_app(settings: Settings | None = None, engine=None):
    engine = engine or create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    settings = settings or Settings(auth_disabled=True)
    app = create_app(session_factory=sf, engine=engine, seed=False, settings=settings)

    def override():
        with sf() as s:
            yield s

    app.dependency_overrides[database.get_db] = override
    return app


@pytest.fixture
def open_client():
    with TestClient(make_app()) as c:
        yield c


@pytest.fixture
def authed_app():
    return make_app(Settings(auth_password=PW, auth_disabled=False, session_secret="s" * 32))


# ── request id ──────────────────────────────────────────────────────────
def test_request_id_generated_and_echoed(open_client):
    r = open_client.get("/api/health")
    rid = r.headers["x-request-id"]
    assert OBS.valid_request_id(rid) == rid and len(rid) == 32


def test_request_id_accepted_when_sane(open_client):
    r = open_client.get("/api/health", headers={"X-Request-ID": "abc-123_DEF.456"})
    assert r.headers["x-request-id"] == "abc-123_DEF.456"


@pytest.mark.parametrize(
    "bad",
    ["short", "a" * 65, "has space in it", "semi;colon;123", "uniécode-id-1", "<script>alert(1)</script>", "x" * 500],
)
def test_request_id_rejected_and_replaced(open_client, bad):
    r = open_client.get("/api/health", headers={"X-Request-ID": bad.encode("latin-1", "ignore")})
    assert r.headers["x-request-id"] != bad
    assert OBS.valid_request_id(r.headers["x-request-id"])


@pytest.mark.parametrize("bad", ["abcdefgh\r\nSet-Cookie: x=1", "abcdefgh\nInjected: 1", "abcdefgh\x00", None, ""])
def test_valid_request_id_rejects_injection(bad):
    assert OBS.valid_request_id(bad) is None


def test_request_id_in_contextvar_and_app_logs(logs):
    seen = {}
    app = make_app()

    @app.get("/api/_probe")
    def probe():
        seen["rid"] = OBS.current_request_id()
        logging.getLogger("superteacher.test").warning("hello from handler")
        return {}

    app.router.routes.insert(0, app.router.routes.pop())  # ensure it is matched before any catch-all
    with TestClient(app) as c:
        r = c.get("/api/_probe", headers={"X-Request-ID": "req-12345678"})
    assert seen["rid"] == "req-12345678" == r.headers["x-request-id"]
    line = next(e for e in logs.events() if e.get("msg") == "hello from handler")
    assert line["request_id"] == "req-12345678"
    assert OBS.current_request_id() is None


# ── log schema ──────────────────────────────────────────────────────────
def test_access_log_schema_and_template(logs):
    with TestClient(make_app()) as c:
        r = c.get("/api/version?name=Alice&score=97")
    (e,) = [x for x in logs.events("http_request") if x["route"] == "/api/version"]
    assert set(e) == {
        "ts",
        "level",
        "logger",
        "request_id",
        "event",
        "method",
        "route",
        "status",
        "duration_ms",
        "severity",
    }
    assert e["method"] == "GET" and e["status"] == 200 and e["request_id"] == r.headers["x-request-id"]
    assert isinstance(e["duration_ms"], float) and e["ts"].endswith("+00:00")
    assert e["logger"] == "superteacher.access"
    assert "Alice" not in "".join(logs.lines) and "97" not in e["route"]


def test_route_template_not_raw_path(logs, seeded):
    h = Capture()
    logging.getLogger().addHandler(h)
    try:
        with seeded.app.state.session_factory() as db:
            sid = db.query(Student).first().id
        assert seeded.get(f"/api/students/{sid}").status_code == 200
    finally:
        logging.getLogger().removeHandler(h)
    routes = {e["route"] for e in h.events("http_request")}
    assert "/api/students/{student_id}" in routes
    assert sid not in "".join(line for line in h.lines if '"logger":"superteacher' in line)
    assert sid not in REG.render()


def test_probe_routes_log_at_debug(logs, open_client):
    open_client.get("/api/health")
    (e,) = [x for x in logs.events("http_request") if x["route"] == "/api/health"]
    assert e["level"] == "DEBUG"


def test_5xx_is_error_level_and_counted(logs):
    app = make_app()

    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret student note: Alice failed")

    app.router.routes.insert(0, app.router.routes.pop())
    before = REG.value("st_http_requests_total", method="GET", route="/api/_boom", status_class="5xx")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/_boom").status_code == 500
    (e,) = [x for x in logs.events("http_request") if x["route"] == "/api/_boom"]
    assert e["level"] == "ERROR" and e["status"] == 500
    assert REG.value("st_http_requests_total", method="GET", route="/api/_boom", status_class="5xx") == before + 1


# ── redaction ───────────────────────────────────────────────────────────
SECRETS = ["hunter2-passcode", "sessionTOKENvalue12345", "sk-ant-api03-ABCDEFGHIJKLMNOP", "Zm9vOmJhcg-basic-cred"]


def test_request_with_secrets_never_reaches_logs(logs, authed_app):
    with TestClient(authed_app, base_url="http://testserver") as c:
        r = c.post(
            f"/api/auth/login?passcode={SECRETS[0]}&api_key={SECRETS[2]}",
            json={"password": SECRETS[0], "note": "Alice scored 12/100"},
            headers={
                **H,
                "Authorization": f"Bearer {SECRETS[1]}",
                "Cookie": f"st_session={SECRETS[1]}",
                "X-Api-Key": SECRETS[2],
                "Proxy-Authorization": f"Basic {SECRETS[3]}",
            },
        )
    assert r.status_code == 401
    blob = "\n".join(logs.lines) + REG.render()
    for s in [*SECRETS, "Alice", "12/100", "passcode", "api_key"]:
        assert s not in blob
    assert logs.events("http_request")


def test_formatter_redacts_free_form_messages(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_password", "a passphrase with spaces")
    fmt = observability.JsonFormatter()
    msgs = [
        f"login failed password={SECRETS[0]} for x",
        f'{{"password": "{SECRETS[0]}"}}',
        f"Authorization: Bearer {SECRETS[1]}",
        f"Cookie: st_session={SECRETS[1]}; other=1",
        f"key {SECRETS[2]} leaked",
        "GET /api/students?name=Alice&x=1 failed",
        "user typed a passphrase with spaces here",
        "tok " + "A" * 60,
    ]
    for m in msgs:
        rec = logging.LogRecord("x", logging.WARNING, __file__, 1, m, None, None)
        out = fmt.format(rec)
        for s in (*SECRETS, "Alice", "a passphrase with spaces", "A" * 60):
            assert s not in out, (m, out)
        json.loads(out)


def test_formatter_truncates_and_redacts_exceptions():
    try:
        raise ValueError(f"bad password={SECRETS[0]} " + "z " * 5000)
    except ValueError:
        import sys

        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "x " * 2500, None, sys.exc_info())
    out = json.loads(observability.JsonFormatter().format(rec))
    assert len(out["msg"]) < 1100 and "truncated" in out["msg"]
    assert SECRETS[0] not in out["exc"] and len(out["exc"]) < 4100 and out["exc_type"] == "ValueError"


# ── metrics ─────────────────────────────────────────────────────────────
def test_counters_and_histogram_move(open_client):
    labels = {"method": "GET", "route": "/api/version", "status_class": "2xx"}
    before = REG.value("st_http_requests_total", **labels)
    hist_before = REG.value("st_http_request_duration_seconds", route="/api/version")
    for _ in range(3):
        open_client.get("/api/version")
    assert REG.value("st_http_requests_total", **labels) == before + 3
    assert REG.value("st_http_request_duration_seconds", route="/api/version") == hist_before + 3
    body = REG.render()
    assert 'st_http_request_duration_seconds_bucket{route="/api/version",le="+Inf"}' in body
    assert "# TYPE st_http_requests_total counter" in body


def test_route_cardinality_bounded_under_fuzz(open_client):
    rng = random.Random(7)
    before = set(REG.series("st_http_requests_total"))
    for _ in range(300):
        path = "/" + "/".join(
            "".join(rng.choices(string.ascii_letters + string.digits + "-_%.", k=rng.randint(1, 12)))
            for _ in range(rng.randint(1, 5))
        )
        open_client.request(rng.choice(["GET", "POST", "DELETE", "PATCH"]), path + "?q=" + path, headers=H)
    new = set(REG.series("st_http_requests_total")) - before
    routes = {k[1] for k in new}
    assert routes <= {"unmatched"} | {r.path for r in open_client.app.routes if hasattr(r, "path")}
    assert len(new) <= 4 * 4 * 2  # methods x status classes, one route label
    assert not any(c.isdigit() and len(k[1]) > 40 for k in new for c in k[1])


def test_unknown_method_bucketed():
    reg = observability.Registry()
    mw = observability.ObservabilityMiddleware(None, reg)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    mw.app = app

    async def run():
        for i in range(50):
            await mw({"type": "http", "method": f"WEIRD{i}", "headers": []}, None, lambda m: asyncio.sleep(0))

    asyncio.run(run())
    assert {k[0] for k in reg.series("st_http_requests_total")} == {"OTHER"}


def test_series_cap_is_enforced():
    reg = observability.Registry()
    for i in range(observability.MAX_SERIES + 50):
        reg.inc("st_ai_calls_total", (f"k{i}", "ok"))
    assert len(reg.series("st_ai_calls_total")) == observability.MAX_SERIES
    assert reg.value("st_metrics_dropped_series_total") == 50


def test_route_label_cap():
    reg = observability.Registry()
    got = {reg.bound_route(f"/r{i}") for i in range(observability.MAX_ROUTES + 20)}
    assert "other" in got and len(got) == observability.MAX_ROUTES + 1


def test_login_failures_and_lockouts_counted(authed_app):
    f0, l0 = REG.value("st_login_failures_total"), REG.value("st_login_lockouts_total")
    with TestClient(authed_app, base_url="http://testserver") as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"password": "nope"}, headers=H).status_code == 401
        assert c.post("/api/auth/login", json={"password": "nope"}, headers=H).status_code == 429
    assert REG.value("st_login_failures_total") == f0 + 5
    assert REG.value("st_login_lockouts_total") == l0 + 1


# ── AI instrumentation ──────────────────────────────────────────────────
def ai_val(kind, outcome):
    return REG.value("st_ai_calls_total", kind=kind, outcome=outcome)


def test_ai_call_context_manager(logs):
    ok0, err0, to0 = ai_val("chat", "ok"), ai_val("chat", "error"), ai_val("chat", "timeout")
    with observability.ai_call("chat"):
        pass
    with pytest.raises(RuntimeError), observability.ai_call("chat"):
        raise RuntimeError("boom with Alice's notes")
    with pytest.raises(TimeoutError), observability.ai_call("chat"):
        raise TimeoutError
    assert (ai_val("chat", "ok"), ai_val("chat", "error"), ai_val("chat", "timeout")) == (ok0 + 1, err0 + 1, to0 + 1)
    assert REG.value("st_ai_call_seconds", kind="chat") >= 3
    assert "Alice" not in "".join(logs.lines)


def test_record_ai_call_normalises_labels():
    observability.record_ai_call("totally-new-kind", "weird", 0.1)
    assert ai_val("other", "error") >= 1


def test_ai_chat_insight_and_parent_update_instrumented(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test-not-real")
    c_ok, c_err = ai_val("chat", "ok"), ai_val("chat", "error")
    monkeypatch.setattr(ai, "client", lambda: FakeAI(turns=[end_turn("hi")]))

    async def chat():
        return [e async for e in ai.run_chat([{"role": "user", "content": "hi"}], "roster")]

    asyncio.run(chat())
    monkeypatch.setattr(
        ai,
        "client",
        lambda: FakeAI(turns=[__import__("tests.ai_fakes", fromlist=["x"]).FakeStream([], "end_turn", [])]),
    )
    f = FakeAI(turns=[])
    f.stream = lambda **kw: (_ for _ in ()).throw(api_error(__import__("anthropic").APIStatusError, 500))
    monkeypatch.setattr(ai, "client", lambda: f)
    with pytest.raises(ai.ChatError):
        asyncio.run(chat())
    assert ai_val("chat", "ok") == c_ok + 1 and ai_val("chat", "error") == c_err + 1

    # insight: invalid JSON thrice -> fallback; valid -> ok
    async def nosleep(_):
        pass

    monkeypatch.setattr(ai, "_sleep", nosleep)
    i_fb, i_ok = ai_val("insight", "fallback"), ai_val("insight", "ok")
    with seeded.app.state.session_factory() as db:
        students = db.query(Student).limit(2).all()
        monkeypatch.setattr(ai, "client", lambda: FakeAI(creates=["nope"] * 3))
        asyncio.run(ai.ai_insight(db, students[0]))
        good = json.dumps({"headline": "Doing well", "strengths": ["a"], "concerns": [], "actions": ["x"]})
        monkeypatch.setattr(ai, "client", lambda: FakeAI(creates=[good]))
        asyncio.run(ai.ai_insight(db, students[1]))
    assert ai_val("insight", "fallback") == i_fb + 1
    assert ai_val("insight", "ok") + ai_val("insight", "fallback") >= i_ok + i_fb + 2

    # parent update: failure -> template -> fallback
    p_fb = ai_val("parent_update", "fallback")
    monkeypatch.setattr(reports, "make_client", lambda: FakeAI(creates=[RuntimeError("x")]))
    with seeded.app.state.session_factory() as db:
        s = db.query(Student).first()
        _draft, source = asyncio.run(reports.parent_update(s, "warm"))
    assert source == "template" and ai_val("parent_update", "fallback") == p_fb + 1


def test_unconfigured_ai_is_not_recorded(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    before = sum(REG.series("st_ai_calls_total").values())
    monkeypatch.setattr(ai, "client", lambda: None)

    async def chat():
        return [e async for e in ai.run_chat([{"role": "user", "content": "hi"}], "r")]

    asyncio.run(chat())
    assert sum(REG.series("st_ai_calls_total").values()) == before


# ── WebSocket ───────────────────────────────────────────────────────────
def test_websocket_works_with_middleware_and_is_logged(logs, seeded, monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI(turns=[end_turn("he", "llo")]))
    open0 = REG.value("st_websocket_connections_open")
    with seeded.websocket_connect("/api/chat/ws", headers={"X-Request-ID": "ws-req-12345"}) as ws:
        assert REG.value("st_websocket_connections_open") == open0 + 1
        ws.send_json({"content": "hello"})
        types = []
        while True:
            ev = ws.receive_json()
            types.append(ev["type"])
            if ev["type"] in ("done", "error"):
                break
        assert "delta" in types
    assert REG.value("st_websocket_connections_open") == open0
    (o,) = logs.events("ws_open")
    (cl,) = logs.events("ws_close")
    assert o["route"] == cl["route"] == "/api/chat/ws" and o["request_id"] == "ws-req-12345"
    assert cl["accepted"] is True and cl["duration_ms"] >= 0
    assert "hello" not in "".join(logs.lines)


def test_rejected_websocket_logged_not_open(logs, authed_app):
    from starlette.websockets import WebSocketDisconnect

    rej0 = REG.value("st_websocket_connections_total", outcome="rejected")
    with (
        TestClient(authed_app, base_url="http://testserver") as c,
        pytest.raises(WebSocketDisconnect),
        c.websocket_connect("/api/chat/ws"),
    ):
        pass
    assert REG.value("st_websocket_connections_total", outcome="rejected") == rej0 + 1
    assert logs.events("ws_close")[-1]["accepted"] is False
    assert REG.value("st_websocket_connections_open") == 0


# ── /api/ready ──────────────────────────────────────────────────────────
def test_ready_healthy_memory_db(open_client):
    r = open_client.get("/api/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"database": "ok", "migrations": "n/a"}}


def test_ready_public_even_with_auth(authed_app):
    with TestClient(authed_app, base_url="http://testserver") as c:
        assert c.get("/api/ready").status_code == 200
        assert c.get("/api/health").status_code == 200


def test_ready_file_db_at_head_then_behind(tmp_path):
    eng = database.make_engine(f"sqlite:///{tmp_path}/t.db")
    with TestClient(make_app(engine=eng)) as c:
        r = c.get("/api/ready")
        assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "migrations": "ok"}
        with eng.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num='deadbeef0000'"))
        r = c.get("/api/ready")
        assert r.status_code == 503
        assert r.json() == {"status": "not_ready", "checks": {"database": "ok", "migrations": "behind"}}
        assert "deadbeef" not in r.text
        assert c.get("/api/health").status_code == 200  # liveness unaffected


def test_ready_unhealthy_db_is_sanitized(open_client):
    def broken():
        raise RuntimeError("password=hunter2 host=10.0.0.5 secret-detail")

    open_client.app.state.session_factory = broken
    r = open_client.get("/api/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "checks": {"database": "error", "migrations": "unknown"}}
    assert "hunter2" not in r.text and "10.0.0.5" not in r.text


# ── /api/metrics auth ───────────────────────────────────────────────────
def test_metrics_requires_session(authed_app):
    with TestClient(authed_app, base_url="http://testserver") as c:
        assert c.get("/api/metrics").status_code == 401
        assert c.post("/api/auth/login", json={"password": PW}, headers=H).status_code == 200
        r = c.get("/api/metrics")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain; version=0.0.4")
        assert "# TYPE st_http_requests_total counter" in r.text and "st_websocket_connections_open" in r.text


def test_metrics_bearer_token(authed_app, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "scrape-token-abcdef123")
    with TestClient(authed_app, base_url="http://testserver") as c:
        assert c.get("/api/metrics", headers={"Authorization": "Bearer scrape-token-abcdef123"}).status_code == 200
        assert c.get("/api/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/metrics").status_code == 401
        # a bearer token does not unlock any other route
        assert c.get("/api/students", headers={"Authorization": "Bearer scrape-token-abcdef123"}).status_code == 401


def test_metrics_token_unset_means_bearer_ignored(authed_app, monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    with TestClient(authed_app, base_url="http://testserver") as c:
        assert c.get("/api/metrics", headers={"Authorization": "Bearer "}).status_code == 401


def test_metrics_open_only_when_auth_disabled(open_client):
    assert open_client.get("/api/metrics").status_code == 200


def test_redaction_covers_accounts_secrets_and_emails():
    from superteacher import observability as o

    link = "http://x/auth/verify#token=abcDEF123_-abcDEF123_-abcDEF123_-abcDEF123"
    out = o.redact(f"sent {link} to Jane.Doe+x@School.example.org with SG.abcdefgh12345678.ijklmnop12345678")
    assert "abcDEF123" not in out and "Jane" not in out and "School.example.org" not in out and "SG." not in out
    assert "[REDACTED-EMAIL]" in out


def test_redaction_knows_the_sendgrid_setting(monkeypatch):
    from superteacher import observability as o
    from superteacher.config import get_settings

    monkeypatch.setattr(get_settings(), "sendgrid_api_key", "not-a-real-key-123", raising=False)
    assert "not-a-real-key-123" not in o.redact("auth failed for key not-a-real-key-123")
