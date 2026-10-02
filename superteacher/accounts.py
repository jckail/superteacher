"""Accounts service layer: email normalisation, one-time login tokens, server-side sessions, quotas, tenancy helpers.

Secrets (login tokens, session ids) are 256-bit random values that only ever leave the server inside an email link
or an HttpOnly cookie. The database holds their SHA-256 hash, so a leaked database (or Litestream replica) cannot be
replayed, and lookup by hash is the constant-time comparison. Nothing here logs an email address or a secret.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .config import Settings
from .models import (
    OWNER_EMAIL,
    OWNER_ID,
    AiBudget,
    AuthSession,
    LoginToken,
    UsageCounter,
    User,
)

TOUCH_EVERY = timedelta(minutes=1)  # last_seen_at is written at most this often

_LOCAL = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+$")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def now() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


# ── secrets ─────────────────────────────────────────────────────────────
def new_secret() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def hash_ip(key: bytes, ip: str) -> str:
    return hmac.new(key, b"ip:" + ip.encode(), hashlib.sha256).hexdigest()


# ── email ───────────────────────────────────────────────────────────────
def normalize_email(raw: object) -> str | None:
    """NFKC + strip + lower-case; None if it is not a plausible single address. No DNS, no quoted locals."""
    if not isinstance(raw, str) or len(raw) > 320:
        return None
    s = unicodedata.normalize("NFKC", raw).strip().lower()
    if not s or len(s) > 254 or any(unicodedata.category(c)[0] in "CZ" for c in s):
        return None
    local, sep, domain = s.rpartition("@")
    if not sep or not 0 < len(local) <= 64 or ".." in local or local[0] == "." or local[-1] == ".":
        return None
    if not _LOCAL.match(local):
        return None
    labels = domain.split(".")
    if (
        len(labels) < 2
        or not all(_LABEL.match(x) for x in labels)
        or not re.match(r"^(?:[a-z]{2,}|xn--[a-z0-9-]+)$", labels[-1])
    ):
        return None
    return s


def allowed_domain(settings: Settings, email: str) -> bool:
    allow = {d.strip().lower().lstrip("@") for d in settings.accounts_email_allowlist_domains.split(",") if d.strip()}
    return not allow or email.rpartition("@")[2] in allow


# ── rate limiting (in-process; the per-email limit is database backed) ───
class SlidingWindow:
    """At most ``limit`` hits per ``window`` seconds for each key. Memory is bounded."""

    def __init__(self, limit: int, window: float = 3600.0, clock=time.monotonic, max_keys: int = 20_000):
        self.limit, self.window, self.clock, self.max_keys = limit, window, clock, max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], t: float) -> None:
        while q and t - q[0] >= self.window:
            q.popleft()

    def allow(self, key: str) -> bool:
        t = self.clock()
        with self._lock:
            if len(self._hits) > self.max_keys:
                for k in [k for k, q in self._hits.items() if not q or t - q[-1] >= self.window]:
                    del self._hits[k]
            q = self._hits.setdefault(key, deque())
            self._prune(q, t)
            if len(q) >= self.limit:
                return False
            q.append(t)
            return True

    def retry_after(self, key: str) -> int:
        t = self.clock()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            self._prune(q, t)
            return max(1, int(q[0] + self.window - t) + 1) if q else 0


# ── users ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str


def ensure_owner(db: Session) -> str:
    """The implicit user behind passcode mode (and pre-accounts data). Idempotent."""
    owner = db.get(User, OWNER_ID)
    if owner is None:
        db.add(User(id=OWNER_ID, email=OWNER_EMAIL, disabled=False))
        db.commit()
    return OWNER_ID


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.id != OWNER_ID)) or 0


def find_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_or_create_user(db: Session, settings: Settings, email: str) -> tuple[User, bool] | None:
    """The user for a verified email, creating it (and its starter classroom) on first use.

    None when the address may not sign up (user cap reached). Returns (user, created).
    """
    from .seed import seed_starter

    user = find_user(db, email)
    if user:
        return user, False
    owner_email = (settings.accounts_owner_email or "").strip().lower()
    legacy = db.get(User, OWNER_ID)
    if owner_email and email == owner_email and legacy is not None and legacy.email == OWNER_EMAIL:
        legacy.email = email  # the deployment owner adopts the data created before accounts existed
        db.commit()
        return legacy, False
    if count_users(db) >= settings.accounts_max_users:
        return None
    user = User(email=email, disabled=False)
    db.add(user)
    db.commit()
    seed_starter(db, user.id)
    return user, True


# ── login tokens ────────────────────────────────────────────────────────
def issue_login_token(db: Session, settings: Settings, email: str, ip_hash: str | None) -> str:
    """Add (not commit) a token row and return the raw token. The caller commits or rolls back."""
    raw = new_secret()
    t = now()
    db.add(
        LoginToken(
            token_hash=hash_secret(raw),
            email=email,
            created_at=t,
            expires_at=t + timedelta(minutes=settings.login_token_ttl_minutes),
            ip_hash=ip_hash,
        )
    )
    db.flush()
    return raw


def recent_token_count(db: Session, email: str, window: timedelta = timedelta(hours=1)) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(LoginToken)
            .where(LoginToken.email == email, LoginToken.created_at > now() - window)
        )
        or 0
    )


def consume_login_token(db: Session, raw: str) -> str | None:
    """Atomically spend a token. Returns the email, or None if unknown / expired / already used / tampered."""
    h = hash_secret(raw)
    t = now()
    res = db.execute(
        update(LoginToken)
        .where(LoginToken.token_hash == h, LoginToken.consumed_at.is_(None), LoginToken.expires_at > t)
        .values(consumed_at=t)
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        db.rollback()
        return None
    email = db.scalar(select(LoginToken.email).where(LoginToken.token_hash == h))
    db.commit()
    return email


def purge_expired(db: Session) -> None:
    cutoff = now() - timedelta(days=1)
    db.execute(delete(LoginToken).where(LoginToken.expires_at < cutoff))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    db.commit()


# ── sessions ────────────────────────────────────────────────────────────
def create_session(db: Session, settings: Settings, user: User) -> str:
    raw = new_secret()
    t = now()
    db.add(
        AuthSession(
            id_hash=hash_secret(raw),
            user_id=user.id,
            created_at=t,
            last_seen_at=t,
            expires_at=t + timedelta(hours=settings.accounts_session_absolute_hours),
        )
    )
    user.last_login_at = t
    db.commit()
    return raw


def resolve_session(db: Session, settings: Settings, raw: str | None) -> CurrentUser | None:
    """The user behind a cookie value, enforcing absolute + idle expiry and the disabled flag."""
    if not raw or len(raw) > 200:
        return None
    row = db.get(AuthSession, hash_secret(raw))
    if row is None:
        return None
    t = now()
    idle = timedelta(hours=settings.accounts_session_idle_hours)
    if aware(row.expires_at) <= t or t - aware(row.last_seen_at) > idle:
        db.delete(row)
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or user.disabled:
        return None
    if t - aware(row.last_seen_at) > TOUCH_EVERY:
        row.last_seen_at = t
        db.commit()
    return CurrentUser(id=user.id, email=user.email)


def revoke_session(db: Session, raw: str | None) -> None:
    if raw:
        db.execute(delete(AuthSession).where(AuthSession.id_hash == hash_secret(raw)))
        db.commit()


def revoke_all_sessions(db: Session, user_id: str) -> int:
    n = db.execute(delete(AuthSession).where(AuthSession.user_id == user_id)).rowcount
    db.commit()
    return n or 0


# ── quotas ──────────────────────────────────────────────────────────────
QUOTA_KINDS = ("chat", "insight", "parent_update")


class QuotaExceeded(Exception):
    def __init__(self, kind: str, limit: int, resets_at: datetime, scope: str = "user"):
        self.kind, self.limit, self.resets_at, self.scope = kind, limit, resets_at, scope
        super().__init__(self.message)

    @property
    def message(self) -> str:
        what = {"chat": "chat messages", "insight": "AI insights", "parent_update": "parent drafts"}[self.kind]
        reset = self.resets_at.strftime("%H:%M UTC")
        if self.scope == "global":
            return f"The demo has reached its daily AI budget. It resets at {reset}; please try again then."
        return f"You've used today's {self.limit} {what} on this demo. The limit resets at {reset}."

    @property
    def retry_after(self) -> int:
        return max(1, int((self.resets_at - now()).total_seconds()))


def quota_http_error(e: QuotaExceeded):
    from fastapi import HTTPException

    return HTTPException(
        429,
        {"code": "quota_exceeded", "message": e.message, "kind": e.kind, "resets_at": e.resets_at.isoformat()},
        headers={"Retry-After": str(e.retry_after)},
    )


def quota_limit(settings: Settings, kind: str) -> int:
    return {
        "chat": settings.quota_chat_per_day,
        "insight": settings.quota_insight_per_day,
        "parent_update": settings.quota_parent_update_per_day,
    }[kind]


def next_reset(today: date | None = None) -> datetime:
    d = today or now().date()
    return datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=UTC)


_quota_lock = threading.Lock()


def consume_quota(db: Session, settings: Settings, user_id: str, kind: str) -> None:
    """Count one metered action or raise QuotaExceeded. Called BEFORE the model call, so failures cost quota
    (cheap to reason about, and it keeps retry loops from being free)."""
    today = now().date()
    limit = quota_limit(settings, kind)
    budget = settings.ai_global_daily_budget
    with _quota_lock:  # single process; the DB rows are the durable record
        row = db.get(UsageCounter, (user_id, today, kind))
        used = row.count if row else 0
        if used >= limit:
            raise QuotaExceeded(kind, limit, next_reset(today))
        g = db.get(AiBudget, today)
        if budget is not None and (g.count if g else 0) >= budget:
            raise QuotaExceeded(kind, budget, next_reset(today), scope="global")
        if row:
            row.count += 1
        else:
            db.add(UsageCounter(user_id=user_id, day=today, kind=kind, count=1))
        if g:
            g.count += 1
        else:
            db.add(AiBudget(day=today, count=1))
        db.commit()


def usage_today(db: Session, settings: Settings, user_id: str) -> dict[str, dict[str, int | str]]:
    today = now().date()
    rows = db.execute(
        select(UsageCounter.kind, UsageCounter.count).where(UsageCounter.user_id == user_id, UsageCounter.day == today)
    )
    used = {kind: n for kind, n in rows}  # noqa: C416 (Row objects are not 2-tuples to dict())
    return {
        k: {"used": used.get(k, 0), "limit": quota_limit(settings, k), "resets_at": next_reset(today).isoformat()}
        for k in QUOTA_KINDS
    }
