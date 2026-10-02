"""Authentication: a shared passcode (default) or passwordless email accounts (AUTH_MODE=accounts).

Both modes resolve every request to a ``CurrentUser`` through ONE dependency, :func:`current_user`; passcode mode maps
to the implicit owner user, so ownership scoping is uniform. Accounts mode (sign-in links, server-side revocable
sessions) is documented in ``accounts.py`` and docs/adr/0002. The rest of this docstring describes the passcode design.

Design (server-revocable passcode sessions):
* ``AUTH_PASSWORD`` is the passcode. Login compares in constant time and, on success, sets a signed
  (itsdangerous, HMAC-SHA1 over a key derived from SESSION_SECRET + passcode), HttpOnly, SameSite=Lax
  v2 cookie with a random nonce. Every request also requires its full-cookie hash in AuthSession for the owner.
  Changing the passcode invalidates every session; legacy v1 cookies require signing in again.
  Passcode idle expiry reuses accounts_session_idle_hours, capped by the passcode absolute TTL.
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
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, WebSocketException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.requests import HTTPConnection
from itsdangerous import BadData, URLSafeSerializer, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from . import accounts, mailer
from .accounts import CurrentUser
from .config import Settings
from .models import OWNER_EMAIL, OWNER_ID, AuthSession, User

log = logging.getLogger("superteacher.auth")

COOKIE = "st_session"
CSRF_HEADER = "x-requested-with"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

MAX_FREE_ATTEMPTS = 5
GLOBAL_MAX_ATTEMPTS = 50
LOCK_BASE_SECONDS = 15
LOCK_MAX_SECONDS = 15 * 60
FAILURE_RESET_SECONDS = 30 * 60


def _origin(value: str) -> tuple[str, str, int] | None:
    """Parse a browser origin, rejecting credentials, paths and opaque origins."""
    try:
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


class AuthState:
    """Per-app auth configuration + login throttle."""

    def __init__(self, settings: Settings, secret_dir: Path | None = None):
        self.settings = settings
        self.disabled = settings.auth_disabled
        self.accounts = settings.auth_mode == "accounts"
        if self.accounts and self.disabled:
            raise RuntimeError("AUTH_DISABLED cannot be combined with AUTH_MODE=accounts.")
        if self.accounts:
            mailer.validate_settings(settings)
        if not self.disabled and not self.accounts and not settings.auth_password:
            raise RuntimeError(
                "AUTH_PASSWORD is not set. Set AUTH_PASSWORD (and ideally SESSION_SECRET), or set "
                "AUTH_DISABLED=true to run WITHOUT authentication (local development only)."
            )
        if self.disabled:
            log.warning("AUTH_DISABLED=true: the API is OPEN. Do not expose this to a network.")
        secret = settings.session_secret or self._load_or_create_secret(secret_dir)
        key = hmac.new(secret.encode(), (settings.auth_password or "").encode(), hashlib.sha256).hexdigest()
        self.serializer = URLSafeTimedSerializer(key, salt="superteacher-session")
        self._roster_cursor_serializer = URLSafeSerializer(key, salt="superteacher-roster-page-v1")
        self.key = hmac.new(secret.encode(), b"accounts-ip-hash", hashlib.sha256).digest()
        self.link_ip = accounts.SlidingWindow(settings.accounts_link_per_ip_hour)
        self.link_global = accounts.SlidingWindow(settings.accounts_link_global_hour)
        self.verify_ip = accounts.SlidingWindow(30, window=600.0)
        self._owner_ready = False
        self.ttl = settings.session_ttl_hours * 3600
        self.origins = {origin for o in settings.cors_origins if (origin := _origin(o)) is not None}
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
    def roster_cursor_serializer(self) -> URLSafeSerializer:
        """Sign roster continuations with a purpose distinct from authentication."""
        return self._roster_cursor_serializer

    def issue(self) -> str:
        """Sign a unique v2 cookie. Only a matching live DB row grants access."""
        return self.serializer.dumps({"v": 2, "mode": "passcode", "nonce": accounts.new_secret()})

    def valid(self, token: str | None) -> bool:
        """Validate the signed wire format only, never route authorization."""
        if not isinstance(token, str) or not 1 <= len(token) <= 512:
            return False
        try:
            payload = self.serializer.loads(token, max_age=self.ttl)
            return (
                type(payload) is dict
                and set(payload) == {"v", "mode", "nonce"}
                and type(payload["v"]) is int
                and payload["v"] == 2
                and payload["mode"] == "passcode"
                and accounts.opaque_session(payload["nonce"])
            )
        except BadData:
            return False

    def check_password(self, candidate: str) -> bool:
        a = hashlib.sha256(candidate.encode("utf-8", "surrogatepass")).digest()
        b = hashlib.sha256((self.settings.auth_password or "").encode()).digest()
        return hmac.compare_digest(a, b)

    # --- origins / csrf ---
    def origin_ok(self, conn: HTTPConnection) -> bool:
        origin = conn.headers.get("origin")
        if origin is None:
            return True
        origin = _origin(origin)
        if origin is None:
            return False
        if origin in self.origins:
            return True
        scheme = conn.url.scheme
        scheme = {"ws": "http", "wss": "https"}.get(scheme, scheme)
        return origin == _origin(f"{scheme}://{conn.headers.get('host', '')}")

    # --- throttle ---
    def _lock_remaining(self, key: str) -> int:
        count, last = self._fails.get(key, (0, 0.0))
        if time.monotonic() - last >= FAILURE_RESET_SECONDS:
            self._fails.pop(key, None)
            return 0
        limit = GLOBAL_MAX_ATTEMPTS if key == "*" else MAX_FREE_ATTEMPTS
        if count < limit:
            return 0
        wait = min(LOCK_MAX_SECONDS, LOCK_BASE_SECONDS * 2 ** min(count - limit, 6))
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
                count, last = self._fails.get(k, (0, 0.0))
                self._fails[k] = (1 if now - last >= FAILURE_RESET_SECONDS else count + 1, now)
            if len(self._fails) > 10_000:  # bound memory
                self._fails = {k: v for k, v in self._fails.items() if now - v[1] < FAILURE_RESET_SECONDS}
                while len(self._fails) > 10_000:
                    oldest = next(k for k in self._fails if k != "*")
                    self._fails.pop(oldest)


def _state(conn: HTTPConnection) -> AuthState:
    return conn.app.state.auth


def _secure(request: Request, st: AuthState) -> bool:
    if st.settings.cookie_secure is not None:
        return st.settings.cookie_secure
    # Uvicorn's trusted-proxy middleware sets the scheme. Raw client headers cannot establish HTTPS.
    return request.url.scheme == "https"


def _owner(st: AuthState, factory) -> CurrentUser:
    if not st._owner_ready:
        with factory() as db:
            try:
                accounts.ensure_owner(db)
            except IntegrityError:  # another worker created it first
                db.rollback()
        st._owner_ready = True
    return CurrentUser(OWNER_ID, OWNER_EMAIL, is_legacy=True)


def _resolve(st: AuthState, factory, cookie: str | None, *, touch: bool = True) -> CurrentUser | None:
    if st.accounts:
        with factory() as db:
            return accounts.resolve_session(db, st.settings, cookie, touch=touch)
    if st.disabled:
        return _owner(st, factory)
    if st.valid(cookie):
        with factory() as db:
            return accounts.resolve_session_hash(
                db,
                accounts.hash_secret(cookie),
                idle=timedelta(seconds=min(st.ttl, st.settings.accounts_session_idle_hours * 3600)),
                required_owner=OWNER_ID,
                touch=touch,
            )
    return None


async def current_user(conn: HTTPConnection) -> CurrentUser:
    """THE dependency for every authenticated REST and WebSocket route: origin + CSRF + session -> the user.

    Handlers scope every query to ``user.id``; tests/test_security_routes.py asserts no route skips it.
    """
    st = _state(conn)
    is_ws = conn.scope["type"] == "websocket"
    if not st.disabled and not st.origin_ok(conn):
        if is_ws:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        raise HTTPException(403, "Origin not allowed")
    user = await run_in_threadpool(_resolve, st, conn.app.state.session_factory, conn.cookies.get(COOKIE))
    if user is None:
        if is_ws:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated")
        raise HTTPException(401, "Not authenticated")
    if not st.disabled and not is_ws and conn.scope["method"] not in SAFE_METHODS and CSRF_HEADER not in conn.headers:
        raise HTTPException(403, "Missing CSRF header")
    return user


async def ws_session_active(conn: HTTPConnection, user: CurrentUser, *, touch: bool = False) -> bool:
    """Recheck the original connection cookie, including server revocation and account expiry."""
    current = await run_in_threadpool(
        _resolve, _state(conn), conn.app.state.session_factory, conn.cookies.get(COOKIE), touch=touch
    )
    return current is not None and current.id == user.id


async def require_auth(conn: HTTPConnection) -> None:
    """Back-compat for callers that only need the gate (metrics)."""
    await current_user(conn)


class LoginBody(BaseModel):
    password: str = Field(max_length=1024)


router = APIRouter(prefix="/auth", tags=["auth"])


def settings_of(conn: HTTPConnection) -> Settings:
    return _state(conn).settings


def _csrf(request: Request, st: AuthState) -> None:
    if not st.origin_ok(request) or CSRF_HEADER not in request.headers:
        raise HTTPException(403, "Missing CSRF header")


def _set_cookie(response: Response, request: Request, st: AuthState, value: str, max_age: int) -> None:
    response.set_cookie(
        COOKIE, value, max_age=max_age, httponly=True, samesite="lax", secure=_secure(request, st), path="/"
    )


def clear_cookie(response: Response, request: Request, st: AuthState) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=_secure(request, st))


def _accounts_only(st: AuthState) -> None:
    if not st.accounts:
        raise HTTPException(404, "Not Found")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/config")
def auth_config(request: Request):
    """Public and fixed-shape: tells the sign-in screen which form to show."""
    st = _state(request)
    return {
        "auth_mode": "accounts" if st.accounts else "passcode",
        # False while sign-in email delivery is failing (see mailer.DeliveryHealth). Says nothing about any address.
        "email_available": mailer.email_available() if st.accounts else True,
    }


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    st = _state(request)
    _csrf(request, st)
    if st.accounts:
        raise HTTPException(404, "Not Found")
    if st.disabled:
        return {"authenticated": True, "auth_required": False}
    client = _ip(request)
    wait = st.retry_after(client)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in {wait}s.", headers={"Retry-After": str(wait)})
    ok = st.check_password(body.password)
    st.record(client, ok)
    if not ok:
        raise HTTPException(401, "Incorrect passcode")
    raw = st.issue()
    with request.app.state.session_factory() as db:
        accounts.ensure_owner(db, commit=False)
        owner = db.get(User, OWNER_ID)
        if owner is None or owner.disabled:
            raise HTTPException(401, "Not authenticated")
        presented = request.cookies.get(COOKIE)
        if st.valid(presented):
            db.execute(
                delete(AuthSession).where(
                    AuthSession.id_hash == accounts.hash_secret(presented), AuthSession.user_id == OWNER_ID
                )
            )
        t = accounts.now()
        db.execute(delete(AuthSession).where(AuthSession.user_id == OWNER_ID, AuthSession.expires_at <= t))
        db.add(
            AuthSession(
                id_hash=accounts.hash_secret(raw),
                user_id=OWNER_ID,
                created_at=t,
                last_seen_at=t,
                expires_at=t + timedelta(seconds=st.ttl),
            )
        )
        owner.last_login_at = t
        db.commit()
    _set_cookie(response, request, st, raw, st.ttl)
    return {"authenticated": True, "auth_required": True}


GENERIC_LINK_REPLY = {"status": "ok", "message": "If that address can receive mail, a sign-in link is on its way."}


class RequestLinkBody(BaseModel):
    email: str = Field(max_length=320)


class VerifyBody(BaseModel):
    token: str = Field(min_length=16, max_length=200)


def _link_base(settings: Settings) -> str:
    base = settings.public_base_url or (settings.cors_origins[0] if settings.cors_origins else "")
    return base.rstrip("/")


@router.post("/request-link", status_code=202)
def request_link(body: RequestLinkBody, request: Request, background: BackgroundTasks):
    """Email a one-time sign-in link. The reply never depends on whether the address is known, allowed, rate limited
    per address, or past the user cap: every such case returns the same 202 body after the same work. Only
    address-independent limits (per client address, global) answer 429."""
    st = _state(request)
    _csrf(request, st)
    _accounts_only(st)
    if not mailer.email_available():
        # Address-independent (the breaker watches the provider, not the user), so this leaks nothing about anyone.
        # Better an honest 503 than a "link is on its way" that is not coming.
        raise HTTPException(
            503,
            "Sign-in email is temporarily unavailable. Please try again in a few minutes.",
            headers={"Retry-After": "300"},
        )
    s = st.settings
    ip = _ip(request)
    for window, key in ((st.link_ip, ip), (st.link_global, "*")):
        if not window.allow(key):
            wait = window.retry_after(key)
            raise HTTPException(
                429, "Too many sign-in requests. Please try again later.", headers={"Retry-After": str(wait)}
            )
    email = accounts.normalize_email(body.email)
    if email is None:
        raise HTTPException(422, "Enter a valid email address.")
    with request.app.state.session_factory() as db:
        accounts.purge_expired(db)
        accounts.reserve_link_request(db)
        send = (
            accounts.allowed_domain(s, email)
            and accounts.recent_token_count(db, email) < s.accounts_link_per_email_hour
            and (
                accounts.find_user(db, email) is not None
                or email == accounts.normalize_email(s.accounts_owner_email)
                or accounts.count_users(db) < s.accounts_max_users
            )
        )
        # Same work either way (mint + hash + insert); a dropped request is simply rolled back.
        raw = accounts.issue_login_token(db, s, email, accounts.hash_ip(st.key, ip))
        if send:
            db.commit()
            background.add_task(mailer.send_login_link, s, email, f"{_link_base(s)}/auth/verify#token={raw}")
        else:
            db.rollback()
    return GENERIC_LINK_REPLY


def _session_info(st: AuthState, db, user: CurrentUser) -> dict:
    return {
        "authenticated": True,
        "auth_required": True,
        "auth_mode": "accounts",
        "email": user.email,
        "usage": accounts.usage_today(db, st.settings, user.id),
    }


@router.post("/verify")
def verify(body: VerifyBody, request: Request, response: Response):
    """Spend a sign-in token (POST only: a mail scanner that GETs the link cannot burn it) and start a session."""
    st = _state(request)
    _csrf(request, st)
    _accounts_only(st)
    if not st.verify_ip.allow(accounts.hash_ip(st.key, _ip(request))):
        raise HTTPException(429, "Too many attempts. Try again later.", headers={"Retry-After": "600"})
    bad = HTTPException(400, "This sign-in link is invalid or has expired. Request a new one.")
    with request.app.state.session_factory() as db:
        email = accounts.consume_login_token(db, body.token)
        if email is None:
            raise bad
        got = accounts.get_or_create_user(db, st.settings, email)
        if got is None or got[0].disabled:
            raise bad
        user, created = got
        accounts.revoke_session(db, request.cookies.get(COOKIE))  # rotation: a pre-login cookie never survives
        raw = accounts.create_session(db, st.settings, user)
        _set_cookie(response, request, st, raw, st.settings.accounts_session_absolute_hours * 3600)
        return {**_session_info(st, db, CurrentUser(user.id, user.email)), "new_user": created}


@router.post("/logout")
def logout(request: Request, response: Response):
    st = _state(request)
    _csrf(request, st)
    if st.accounts:
        with request.app.state.session_factory() as db:
            accounts.revoke_session(db, request.cookies.get(COOKIE))  # F-06: the server forgets the session
    elif not st.disabled and st.valid(request.cookies.get(COOKIE)):
        with request.app.state.session_factory() as db:
            db.execute(
                delete(AuthSession).where(
                    AuthSession.id_hash == accounts.hash_secret(request.cookies[COOKIE]),
                    AuthSession.user_id == OWNER_ID,
                )
            )
            db.commit()
    clear_cookie(response, request, st)
    return {"authenticated": False}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: CurrentUser = Depends(current_user)):
    st = _state(request)
    _accounts_only(st)
    with request.app.state.session_factory() as db:
        accounts.revoke_all_sessions(db, user.id)
    clear_cookie(response, request, st)
    return {"authenticated": False}


@router.get("/me")
def me(request: Request):
    st = _state(request)
    if st.disabled:
        return {"authenticated": True, "auth_required": False}
    user = _resolve(st, request.app.state.session_factory, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Not authenticated")
    if st.accounts:
        with request.app.state.session_factory() as db:
            return _session_info(st, db, user)
    return {"authenticated": True, "auth_required": True, "auth_mode": "passcode", "email": None}
