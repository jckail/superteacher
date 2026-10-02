"""Production observability: request ids, structured access logs, redaction, metrics, readiness.

Design rule: this app handles student data, so nothing here ever *reads* a query string, header value
(other than a validated X-Request-ID), cookie, or request/response body. Logs and metrics are built only from
the HTTP method, the matched route TEMPLATE, the status code and timings. A redacting formatter is a second line
of defence for free-form log messages emitted elsewhere in the app.

Registration: ``observability.install(app)`` in ``create_app`` (adds the middleware plus /api/ready and /api/metrics).
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import hmac
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.requests import HTTPConnection
from fastapi.responses import JSONResponse, PlainTextResponse

log = logging.getLogger("superteacher.observability")
access_log = logging.getLogger("superteacher.access")

# ── request id ──────────────────────────────────────────────────────────
REQUEST_ID_HEADER = "x-request-id"
_RID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,63}")  # 8..64 chars, no whitespace/CRLF/odd bytes
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def valid_request_id(value: str | None) -> str | None:
    """Return the id if it is safe to echo/log, else None."""
    if value and _RID_RE.fullmatch(value):
        return value
    return None


def current_request_id() -> str | None:
    return request_id_var.get()


# ── redaction ───────────────────────────────────────────────────────────
MAX_VALUE_CHARS = 1000
MAX_EXC_CHARS = 4000
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = (
    r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|api[_-]?key|passcode|password|passwd|"
    r"secret|token|session|st_session|csrf"
)
_VALUE = r"""(?:"[^"]*"|'[^']*'|[^\s,;&}"']+)"""
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}"), r"\1 " + _REDACTED),
    (re.compile(rf"""(?i)(["']?\b(?:{_SENSITIVE_KEYS})\b["']?\s*[:=]\s*){_VALUE}"""), r"\1" + _REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), _REDACTED),
    (re.compile(r"\bSG\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,})?"), _REDACTED),  # SendGrid API keys
    # accounts: email addresses are personal data and never belong in logs
    (re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"), "[REDACTED-EMAIL]"),
    (re.compile(r"\?[^\s\"'#]+"), "?" + _REDACTED),  # any query string
    (re.compile(r"\b[A-Za-z0-9_-]{40,}(?:\.[A-Za-z0-9_-]{6,}){0,3}"), _REDACTED),  # long opaque tokens / signed cookies
]
_SECRET_SETTINGS = ("auth_password", "anthropic_api_key", "session_secret", "sendgrid_api_key")


def _known_secrets() -> list[str]:
    out = [os.environ.get("METRICS_TOKEN", "")]
    try:
        from .config import get_settings

        s = get_settings()
        out += [str(getattr(s, n, "") or "") for n in _SECRET_SETTINGS]
    except Exception:  # config must never break logging
        pass
    return [v for v in out if len(v) >= 4]


def redact(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    for secret in (*_known_secrets(), *extra_secrets):
        text = text.replace(secret, _REDACTED)
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def clean_value(value: Any, limit: int = MAX_VALUE_CHARS) -> Any:
    if isinstance(value, bool | int | float) or value is None:
        return value
    s = redact(str(value))
    if len(s) > limit:
        s = f"{s[:limit]}...[truncated {len(s) - limit}]"
    return s


_PLAIN_FIELDS = {"ts", "level", "logger", "request_id", "event"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Free-form text is redacted and truncated; structured fields come from record.obs."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
        }
        obs = getattr(record, "obs", None)
        if obs:
            for k, v in obs.items():
                out[k] = v if k in _PLAIN_FIELDS else clean_value(v)
        else:
            out["msg"] = clean_value(record.getMessage())
        if record.exc_info and record.exc_info[0] is not None:
            out["exc_type"] = record.exc_info[0].__name__
            out["exc"] = clean_value(self.formatException(record.exc_info), MAX_EXC_CHARS)
        # Cloud Logging reads "severity"; keep "level" too.
        out["severity"] = record.levelname
        return json.dumps(out, default=str, separators=(",", ":"))


def log_event(level: int, event: str, **fields: Any) -> None:
    access_log.log(level, event, extra={"obs": {"event": event, **fields}})


_configured = False


def configure_logging() -> None:
    """Idempotent: JSON on root stream handlers, request_id on every record, no raw uvicorn access log."""
    global _configured
    if _configured:
        return
    _configured = True
    old_factory = logging.getLogRecordFactory()

    def factory(*a, **kw):
        rec = old_factory(*a, **kw)
        rec.request_id = request_id_var.get()
        return rec

    logging.setLogRecordFactory(factory)
    root = logging.getLogger()
    handlers = [h for h in root.handlers if type(h) is logging.StreamHandler]
    if not handlers:
        h = logging.StreamHandler()
        root.addHandler(h)
        handlers = [h]
    for h in handlers:
        h.setFormatter(JsonFormatter())
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    # uvicorn's access log prints the raw path *and query string*; ours replaces it.
    logging.getLogger("uvicorn.access").disabled = True


# ── metrics registry ────────────────────────────────────────────────────
HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
AI_BUCKETS = (0.5, 1, 2, 5, 10, 20, 30, 60, 120)
WS_BUCKETS = (1, 10, 60, 300, 900, 3600)
MAX_SERIES = 1000
AI_KINDS = ("chat", "insight", "parent_update")
AI_OUTCOMES = ("ok", "error", "timeout", "fallback")
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
UNMATCHED = "unmatched"
MAX_ROUTES = 300


class Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meta: dict[str, tuple[str, str, tuple[str, ...], tuple[float, ...]]] = {}
        self._data: dict[str, dict[tuple[str, ...], Any]] = {}
        self._routes: set[str] = set()
        for name, kind, help_, labels, buckets in (
            ("st_http_requests_total", "counter", "HTTP requests.", ("method", "route", "status_class"), ()),
            (
                "st_http_request_duration_seconds",
                "histogram",
                "HTTP request latency.",
                ("route",),
                HTTP_BUCKETS,
            ),
            ("st_login_failures_total", "counter", "Rejected login attempts (401).", (), ()),
            ("st_login_lockouts_total", "counter", "Login attempts refused by the throttle (429).", (), ()),
            ("st_ai_calls_total", "counter", "AI calls.", ("kind", "outcome"), ()),
            ("st_ai_call_seconds", "histogram", "AI call duration.", ("kind",), AI_BUCKETS),
            ("st_websocket_connections_open", "gauge", "Currently open WebSockets.", (), ()),
            ("st_websocket_connections_total", "counter", "WebSocket handshakes.", ("outcome",), ()),
            ("st_websocket_duration_seconds", "histogram", "WebSocket lifetime.", (), WS_BUCKETS),
            ("st_metrics_dropped_series_total", "counter", "Series dropped by the cardinality cap.", (), ()),
        ):
            self._meta[name] = (kind, help_, labels, buckets)
            self._data[name] = {}

    def reset(self) -> None:
        with self._lock:
            for d in self._data.values():
                d.clear()
            self._routes.clear()

    def bound_route(self, route: str) -> str:
        with self._lock:
            if route in self._routes:
                return route
            if len(self._routes) >= MAX_ROUTES:
                return "other"
            self._routes.add(route)
            return route

    def _series(self, name: str, labels: tuple[str, ...], factory: Callable[[], Any]) -> Any:
        d = self._data[name]
        s = d.get(labels)
        if s is None:
            if len(d) >= MAX_SERIES:
                dropped = self._data["st_metrics_dropped_series_total"]
                dropped[()] = dropped.get((), 0.0) + 1
                return None
            s = d[labels] = factory()
        return s

    def inc(self, name: str, labels: tuple[str, ...] = (), value: float = 1.0) -> None:
        with self._lock:
            d = self._data[name]
            if labels in d:
                d[labels] += value
            elif self._series(name, labels, lambda: 0.0) is not None:
                d[labels] = value

    def gauge_add(self, name: str, value: float) -> None:
        with self._lock:
            d = self._data[name]
            d[()] = max(0.0, d.get((), 0.0) + value)

    def observe(self, name: str, labels: tuple[str, ...], value: float) -> None:
        buckets = self._meta[name][3]
        with self._lock:
            s = self._series(name, labels, lambda: [[0] * len(buckets), 0.0, 0])
            if s is None:
                return
            for i, b in enumerate(buckets):
                if value <= b:
                    s[0][i] += 1
            s[1] += value
            s[2] += 1

    # reads (used by tests and render)
    def value(self, name: str, **labels: str) -> float:
        _, _, names, _ = self._meta[name]
        key = tuple(labels.get(n, "") for n in names)
        with self._lock:
            v = self._data[name].get(key)
        if v is None:
            return 0.0
        return float(v[2]) if isinstance(v, list) else float(v)

    def series(self, name: str) -> dict[tuple[str, ...], Any]:
        with self._lock:
            return dict(self._data[name])

    def render(self) -> str:
        def esc(v: str) -> str:
            return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        def lab(names: tuple[str, ...], vals: tuple[str, ...], extra: str = "") -> str:
            parts = [f'{n}="{esc(v)}"' for n, v in zip(names, vals, strict=True)]
            if extra:
                parts.append(extra)
            return "{" + ",".join(parts) + "}" if parts else ""

        lines: list[str] = []
        with self._lock:
            for name, (kind, help_, names, buckets) in self._meta.items():
                lines += [f"# HELP {name} {help_}", f"# TYPE {name} {kind}"]
                data = self._data[name]
                if not data and kind != "histogram" and not names:
                    lines.append(f"{name} 0")
                for vals, v in sorted(data.items()):
                    if kind == "histogram":
                        for b, c in zip(buckets, v[0], strict=True):
                            le = f'le="{b:g}"'
                            lines.append(f"{name}_bucket{lab(names, vals, le)} {c}")
                        inf = 'le="+Inf"'
                        lines.append(f"{name}_bucket{lab(names, vals, inf)} {v[2]}")
                        lines.append(f"{name}_sum{lab(names, vals)} {v[1]:.6f}")
                        lines.append(f"{name}_count{lab(names, vals)} {v[2]}")
                    else:
                        lines.append(f"{name}{lab(names, vals)} {v:g}")
        return "\n".join(lines) + "\n"


REGISTRY = Registry()


# ── AI instrumentation ──────────────────────────────────────────────────
def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower() or "took too long" in str(exc)


def record_ai_call(kind: str, outcome: str, seconds: float) -> None:
    """Record one AI call. Only the kind, outcome and duration are kept, never prompts or responses."""
    kind = kind if kind in AI_KINDS else "other"
    outcome = outcome if outcome in AI_OUTCOMES else "error"
    REGISTRY.inc("st_ai_calls_total", (kind, outcome))
    REGISTRY.observe("st_ai_call_seconds", (kind,), max(0.0, seconds))
    log_event(logging.INFO, "ai_call", kind=kind, outcome=outcome, seconds=round(seconds, 3))


class _AiCall:
    outcome = "ok"


@contextlib.contextmanager
def ai_call(kind: str) -> Iterator[_AiCall]:
    """``with ai_call("insight") as c: ...``  Set ``c.outcome = "fallback"`` if a degraded result was returned."""
    call, start = _AiCall(), time.perf_counter()
    try:
        yield call
    except BaseException as e:
        if isinstance(e, GeneratorExit | KeyboardInterrupt) or type(e).__name__ == "CancelledError":
            raise  # cancelled by the client: not an AI outcome
        record_ai_call(kind, "timeout" if _is_timeout(e) else "error", time.perf_counter() - start)
        raise
    record_ai_call(kind, call.outcome, time.perf_counter() - start)


def _ai_configured() -> bool:
    from .config import get_settings

    return bool(get_settings().anthropic_api_key)


async def timed_ai(kind: str, coro):
    """Await ``coro``; None result means the call failed and the caller falls back to rules."""
    with ai_call(kind) as c:
        result = await coro
        if result is None:
            c.outcome = "fallback"
        return result


def ai_stream(kind: str):
    """Decorator for an async-generator AI call (chat). Skipped when AI is not configured or the consumer cancels."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            if not _ai_configured():
                async for ev in fn(*a, **kw):
                    yield ev
                return
            start, outcome = time.perf_counter(), "ok"
            try:
                async for ev in fn(*a, **kw):
                    yield ev
            except GeneratorExit:
                outcome = ""
                raise
            except BaseException as e:
                outcome = "" if type(e).__name__ == "CancelledError" else "timeout" if _is_timeout(e) else "error"
                raise
            finally:
                if outcome:
                    record_ai_call(kind, outcome, time.perf_counter() - start)

        return wrapper

    return deco


def ai_observed(kind: str, classify: Callable[[Any], str | None]):
    """Decorator for a coroutine that swallows AI errors and returns a result; ``classify`` maps result -> outcome."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            start = time.perf_counter()
            try:
                result = await fn(*a, **kw)
            except BaseException as e:
                if type(e).__name__ != "CancelledError":
                    record_ai_call(kind, "timeout" if _is_timeout(e) else "error", time.perf_counter() - start)
                raise
            outcome = classify(result)
            if outcome:
                record_ai_call(kind, outcome, time.perf_counter() - start)
            return result

        return wrapper

    return deco


def source_outcome(result: Any) -> str | None:
    """For ``(draft, "ai" | "template")`` results: ok / fallback; None (not recorded) if AI is not configured."""
    if not _ai_configured():
        return None
    return "ok" if result[1] == "ai" else "fallback"


# ── ASGI middleware ─────────────────────────────────────────────────────
_QUIET_ROUTES = {"/api/health", "/api/ready", "/api/metrics"}  # probes/scrapes log at DEBUG


def _route_template(scope) -> str:
    """Matched route template with ids as placeholders, e.g. ``/api/students/{student_id}``.

    Newer FastAPI keeps the include prefix outside ``route.path``; recover it from the concrete path (the prefix is
    static configuration, never user data) so labels are identical across FastAPI versions.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str) or not template.startswith("/"):
        return UNMATCHED
    try:
        relative = getattr(route, "path_format", template).format(**(scope.get("path_params") or {}))
        path = scope.get("path", "")
        if path.endswith(relative):
            prefix = path[: len(path) - len(relative)]
            if prefix and "{" not in prefix and not template.startswith(prefix):
                return prefix + template
    except Exception:  # never let labelling break a request
        pass
    return template


def _status_class(status: int) -> str:
    return f"{status // 100}xx" if 100 <= status <= 599 else "other"


class ObservabilityMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware) so WebSockets and streaming are untouched."""

    def __init__(self, app, registry: Registry = REGISTRY) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        rid = None
        for k, v in scope.get("headers") or ():
            if k == b"x-request-id":
                rid = valid_request_id(v.decode("latin-1"))
                break
        rid = rid or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            if kind == "http":
                await self._http(scope, receive, send, rid)
            else:
                await self._ws(scope, receive, send, rid)
        finally:
            request_id_var.reset(token)

    @staticmethod
    def _with_rid(headers, rid: str) -> list[tuple[bytes, bytes]]:
        kept = [(k, v) for k, v in headers if k.lower() != b"x-request-id"]
        kept.append((b"x-request-id", rid.encode("ascii")))
        return kept

    async def _http(self, scope, receive, send, rid: str) -> None:
        start, status = time.perf_counter(), 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": self._with_rid(message.get("headers") or (), rid)}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            seconds = time.perf_counter() - start
            method = scope.get("method", "")
            method = method if method in HTTP_METHODS else "OTHER"
            route = self.registry.bound_route(_route_template(scope))
            self.registry.inc("st_http_requests_total", (method, route, _status_class(status)))
            self.registry.observe("st_http_request_duration_seconds", (route,), seconds)
            if method == "POST" and route == "/api/auth/login":
                if status == 401:
                    self.registry.inc("st_login_failures_total")
                elif status == 429:
                    self.registry.inc("st_login_lockouts_total")
            level = logging.DEBUG if route in _QUIET_ROUTES else logging.ERROR if status >= 500 else logging.INFO
            log_event(
                level,
                "http_request",
                request_id=rid,
                method=method,
                route=route,
                status=status,
                duration_ms=round(seconds * 1000, 2),
            )

    async def _ws(self, scope, receive, send, rid: str) -> None:
        start = time.perf_counter()
        accepted, code = False, None
        reg = self.registry

        async def receive_wrapper():
            nonlocal code
            message = await receive()
            if message["type"] == "websocket.disconnect":
                code = message.get("code")
            return message

        async def send_wrapper(message):
            nonlocal accepted, code
            if message["type"] == "websocket.accept":
                message = {**message, "headers": self._with_rid(message.get("headers") or (), rid)}
                accepted = True
                reg.gauge_add("st_websocket_connections_open", 1)
                reg.inc("st_websocket_connections_total", ("accepted",))
                log_event(logging.INFO, "ws_open", request_id=rid, route=self._route(scope))
            elif message["type"] == "websocket.close":
                code = message.get("code", 1000)
                if not accepted:
                    reg.inc("st_websocket_connections_total", ("rejected",))
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            seconds = time.perf_counter() - start
            if accepted:
                reg.gauge_add("st_websocket_connections_open", -1)
                reg.observe("st_websocket_duration_seconds", (), seconds)
            log_event(
                logging.INFO,
                "ws_close",
                request_id=rid,
                route=self._route(scope),
                accepted=accepted,
                close_code=code,
                duration_ms=round(seconds * 1000, 2),
            )

    def _route(self, scope) -> str:
        return self.registry.bound_route(_route_template(scope))


# ── endpoints ───────────────────────────────────────────────────────────
router = APIRouter(tags=["system"])


@functools.lru_cache(maxsize=1)
def _alembic_heads() -> frozenset[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from .db import ROOT

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return frozenset(ScriptDirectory.from_config(cfg).get_heads())


def check_readiness(session_factory) -> tuple[bool, dict[str, str]]:
    """Return (ready, checks). Check values are fixed strings: no exception text ever leaves the process."""
    from alembic.migration import MigrationContext
    from sqlalchemy import text

    from . import db as database

    checks = {"database": "error", "migrations": "unknown"}
    try:
        with session_factory() as s:
            s.execute(text("SELECT 1"))
            checks["database"] = "ok"
            eng = s.get_bind()
            if database.is_memory(eng):
                checks["migrations"] = "n/a"  # tests / ephemeral DBs use create_all, not Alembic
            else:
                current = frozenset(MigrationContext.configure(s.connection()).get_current_heads())
                checks["migrations"] = "ok" if current == _alembic_heads() else "behind"
    except Exception as e:
        log.warning("readiness check failed: %s", type(e).__name__)
    return checks["database"] == "ok" and checks["migrations"] in ("ok", "n/a"), checks


@router.get("/ready", include_in_schema=False)
def ready(request: Request):
    ok, checks = check_readiness(request.app.state.session_factory)
    body = {"status": "ready" if ok else "not_ready", "checks": checks}
    return JSONResponse(body, status_code=200 if ok else 503)


async def metrics_auth(conn: HTTPConnection) -> None:
    """Bearer ``METRICS_TOKEN`` (if configured) or a normal session, exactly like the other protected routers."""
    token = os.environ.get("METRICS_TOKEN", "")
    header = conn.headers.get("authorization", "")
    if token and header[:7].lower() == "bearer " and hmac.compare_digest(header[7:].strip(), token):
        return
    from . import auth

    if auth.settings_of(conn).auth_mode == "accounts":
        # Process-wide counters are an operator tool: with many accounts, "any signed-in user" is too broad.
        raise HTTPException(401, "Metrics need the METRICS_TOKEN bearer token")
    await auth.require_auth(conn)


@router.get("/metrics", include_in_schema=False, dependencies=[Depends(metrics_auth)])
def metrics_endpoint():
    return PlainTextResponse(REGISTRY.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


def install(app: FastAPI) -> None:
    """Call once in create_app, AFTER other middleware (so it is outermost) and BEFORE any catch-all route."""
    configure_logging()
    app.include_router(router, prefix="/api")
    app.add_middleware(ObservabilityMiddleware)
