"""Single shared-passcode authentication.

Design (small, auditable, no user table):
* ``AUTH_PASSWORD`` is the passcode. Login compares in constant time and, on success, sets a signed
  (itsdangerous, HMAC-SHA1 over a key derived from SESSION_SECRET + passcode), HttpOnly, SameSite=Lax
  cookie. Changing the passcode invalidates every session.
* ``require_auth`` is a router-level dependency for REST *and* WebSocket routes.
* CSRF: state-changing requests must carry ``X-Requested-With`` (a custom header cannot be sent
  cross-site without a CORS preflight, which CORS_ORIGINS refuses) and, when the browser sends an
  ``Origin``, it must be same-host or in CORS_ORIGINS.
* WebSocket handshakes are checked for the cookie *and* an allowed ``Origin`` (cross-site WS hijacking).
* Login attempts are rate limited with exponential lockout (in-memory, per client address + global).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response, WebSocketException, status
from fastapi.requests import HTTPConnection
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from .config import Settings

log = logging.getLogger("superteacher.auth")

COOKIE = "st_session"
CSRF_HEADER = "x-requested-with"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

MAX_FREE_ATTEMPTS = 5
GLOBAL_MAX_ATTEMPTS = 50
LOCK_BASE_SECONDS = 15
LOCK_MAX_SECONDS = 15 * 60


class AuthState:
    """Per-app auth configuration + login throttle."""

    def __init__(self, settings: Settings, secret_dir: Path | None = None):
        self.settings = settings
        self.disabled = settings.auth_disabled
        if not self.disabled and not settings.auth_password:
            raise RuntimeError(
                "AUTH_PASSWORD is not set. Set AUTH_PASSWORD (and ideally SESSION_SECRET), or set "
                "AUTH_DISABLED=true to run WITHOUT authentication (local development only)."
            )
        if self.disabled:
            log.warning("AUTH_DISABLED=true: the API is OPEN. Do not expose this to a network.")
        secret = settings.session_secret or self._load_or_create_secret(secret_dir)
        key = hmac.new(secret.encode(), (settings.auth_password or "").encode(), hashlib.sha256).hexdigest()
        self.serializer = URLSafeTimedSerializer(key, salt="superteacher-session")
        self.ttl = settings.session_ttl_hours * 3600
        self.origins = {o.rstrip("/").lower() for o in settings.cors_origins}
        self._lock = threading.Lock()
        self._fails: dict[str, tuple[int, float]] = {}  # key -> (consecutive failures, last failure ts)

    @staticmethod
    def _load_or_create_secret(secret_dir: Path | None) -> str:
        if secret_dir is None:
            log.warning(
                "SESSION_SECRET not set and no data directory: using an ephemeral secret "
                "(sessions end on restart and differ across instances)."
            )
            return secrets.token_urlsafe(48)
        f = secret_dir / ".session_secret"
        try:
            if f.exists():
                return f.read_text().strip()
            secret_dir.mkdir(parents=True, exist_ok=True)
            val = secrets.token_urlsafe(48)
            f.write_text(val)
            f.chmod(0o600)
            log.warning(
                "SESSION_SECRET not set: generated one at %s. Set SESSION_SECRET explicitly when "
                "running multiple instances.",
                f,
            )
            return val
        except OSError:
            log.warning("SESSION_SECRET not set and %s is not writable: using an ephemeral secret.", f)
            return secrets.token_urlsafe(48)

    # --- sessions ---
    def issue(self) -> str:
        return self.serializer.dumps({"v": 1})

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            self.serializer.loads(token, max_age=self.ttl)
            return True
        except BadSignature:
            return False

    def check_password(self, candidate: str) -> bool:
        a = hashlib.sha256(candidate.encode()).digest()
        b = hashlib.sha256((self.settings.auth_password or "").encode()).digest()
        return hmac.compare_digest(a, b)

    # --- origins / csrf ---
    def origin_ok(self, conn: HTTPConnection) -> bool:
        origin = conn.headers.get("origin")
        if origin is None:
            return True
        origin = origin.rstrip("/").lower()
        if origin in self.origins:
            return True
        host = (urlparse(origin).netloc or "").lower()
        return bool(host) and host == (conn.headers.get("host") or "").lower()

    # --- throttle ---
    def _lock_remaining(self, key: str) -> int:
        count, last = self._fails.get(key, (0, 0.0))
        limit = GLOBAL_MAX_ATTEMPTS if key == "*" else MAX_FREE_ATTEMPTS
        if count < limit:
            return 0
        wait = min(LOCK_MAX_SECONDS, LOCK_BASE_SECONDS * 2 ** (count - limit))
        return max(0, int(last + wait - time.monotonic()) + 1)

    def retry_after(self, client: str) -> int:
        with self._lock:
            return max(self._lock_remaining(client), self._lock_remaining("*"))

    def record(self, client: str, ok: bool) -> None:
        with self._lock:
            if ok:
                self._fails.pop(client, None)
                return
            now = time.monotonic()
            for k in (client, "*"):
                self._fails[k] = (self._fails.get(k, (0, 0.0))[0] + 1, now)
            if len(self._fails) > 10_000:  # bound memory
                self._fails = {k: v for k, v in self._fails.items() if now - v[1] < LOCK_MAX_SECONDS}


def _state(conn: HTTPConnection) -> AuthState:
    return conn.app.state.auth


def _secure(request: Request, st: AuthState) -> bool:
    if st.settings.cookie_secure is not None:
        return st.settings.cookie_secure
    return (
        request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    )


async def require_auth(conn: HTTPConnection) -> None:
    """Router dependency for REST and WebSocket routes."""
    st = _state(conn)
    if st.disabled:
        return
    is_ws = conn.scope["type"] == "websocket"
    if not st.origin_ok(conn):
        if is_ws:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        raise HTTPException(403, "Origin not allowed")
    if not st.valid(conn.cookies.get(COOKIE)):
        if is_ws:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated")
        raise HTTPException(401, "Not authenticated")
    if not is_ws and conn.scope["method"] not in SAFE_METHODS and CSRF_HEADER not in conn.headers:
        raise HTTPException(403, "Missing CSRF header")


class LoginBody(BaseModel):
    password: str


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    st = _state(request)
    if not st.origin_ok(request) or CSRF_HEADER not in request.headers:
        raise HTTPException(403, "Missing CSRF header")
    if st.disabled:
        return {"authenticated": True, "auth_required": False}
    client = request.client.host if request.client else "unknown"
    wait = st.retry_after(client)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in {wait}s.", headers={"Retry-After": str(wait)})
    ok = st.check_password(body.password)
    st.record(client, ok)
    if not ok:
        raise HTTPException(401, "Incorrect passcode")
    response.set_cookie(
        COOKIE, st.issue(), max_age=st.ttl, httponly=True, samesite="lax", secure=_secure(request, st), path="/"
    )
    return {"authenticated": True, "auth_required": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    st = _state(request)
    if not st.origin_ok(request) or CSRF_HEADER not in request.headers:
        raise HTTPException(403, "Missing CSRF header")
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=_secure(request, st))
    return {"authenticated": False}


@router.get("/me")
def me(request: Request):
    st = _state(request)
    if st.disabled:
        return {"authenticated": True, "auth_required": False}
    if not st.valid(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Not authenticated")
    return {"authenticated": True, "auth_required": True}
