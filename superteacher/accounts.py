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

from sqlalchemy import case, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
            if len(self._hits) >= self.max_keys:
                for k in [k for k, q in self._hits.items() if not q or t - q[-1] >= self.window]:
                    del self._hits[k]
                if key not in self._hits and len(self._hits) >= self.max_keys:
                    return False
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
    is_legacy: bool = False


def _insert(db: Session, model):
    return postgres_insert(model) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(model)


def _reserve_signups(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    else:
        db.execute(update(User).where(User.id == OWNER_ID).values(id=User.id))


def reserve_link_request(db: Session) -> None:
    """Serialize the per-email limit check and token issuance until commit."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE login_tokens IN SHARE ROW EXCLUSIVE MODE"))
    else:
        db.execute(update(LoginToken).where(LoginToken.token_hash == "").values(token_hash=LoginToken.token_hash))


def ensure_owner(db: Session, *, commit: bool = True) -> str:
    """The implicit user behind passcode mode (and pre-accounts data). Idempotent."""
    if db.get(User, OWNER_ID) is not None:
        return OWNER_ID
    db.execute(
        _insert(db, User)
        .values(id=OWNER_ID, email=OWNER_EMAIL, disabled=False)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    if commit:
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

    # SQLite reserves the writer before checking identity/cap, including when
    # the legacy owner does not exist. Concurrent workers cannot both sign up
    # past the cap or seed the same newly created account.
    _reserve_signups(db)
    user = find_user(db, email)
    if user:
        db.commit()
        return user, False
    owner_email = normalize_email(settings.accounts_owner_email or "")
    legacy = db.get(User, OWNER_ID)
    if owner_email and email == owner_email and legacy is not None and legacy.email == OWNER_EMAIL:
        legacy.email = email  # the deployment owner adopts the data created before accounts existed
        db.commit()
        return legacy, False
    if count_users(db) >= settings.accounts_max_users:
        db.rollback()
        return None
    user = User(email=email, disabled=False)
    db.add(user)
    db.flush()
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


def opaque_session(raw: str | None) -> bool:
    """Accounts cookies have exactly the wire format produced by new_secret()."""
    return isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) is not None


def resolve_session_hash(
    db: Session, id_hash: str, *, idle: timedelta, required_owner: str | None = None, touch: bool = True
) -> CurrentUser | None:
    """Resolve a trusted hash; mode-specific callers validate the wire value first."""
    row = db.get(AuthSession, id_hash)
    if row is None or (required_owner is not None and row.user_id != required_owner):
        return None
    t = now()
    owner_condition = AuthSession.user_id == row.user_id
    if aware(row.expires_at) <= t or t - aware(row.last_seen_at) > idle:
        if touch:
            db.execute(
                delete(AuthSession).where(
                    AuthSession.id_hash == id_hash,
                    owner_condition,
                    or_(AuthSession.expires_at <= t, AuthSession.last_seen_at < t - idle),
                ),
                execution_options={"synchronize_session": False},
            )
            db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or user.disabled:
        return None
    if touch and t - aware(row.last_seen_at) > TOUCH_EVERY:
        # A concurrent logout must not resurrect a row; delayed readers must not regress newer activity.
        changed = db.execute(
            update(AuthSession)
            .where(
                AuthSession.id_hash == id_hash,
                owner_condition,
                AuthSession.expires_at > t,
                AuthSession.last_seen_at >= t - idle,
            )
            .values(last_seen_at=case((AuthSession.last_seen_at < t, t), else_=AuthSession.last_seen_at)),
            execution_options={"synchronize_session": False},
        ).rowcount
        db.commit()
        if changed != 1:
            return None
    return CurrentUser(id=user.id, email=user.email, is_legacy=required_owner is not None)


def resolve_session(db: Session, settings: Settings, raw: str | None, *, touch: bool = True) -> CurrentUser | None:
    """Accounts wire format + shared absolute/idle/user policy."""
    if not opaque_session(raw):
        return None
    return resolve_session_hash(
        db, hash_secret(raw), idle=timedelta(hours=settings.accounts_session_idle_hours), touch=touch
    )


def revoke_session(db: Session, raw: str | None) -> None:
    if opaque_session(raw):
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


def consume_quota(db: Session, settings: Settings, user_id: str, kind: str) -> None:
    """Count one metered action or raise QuotaExceeded. Called BEFORE the model call, so failures cost quota
    (cheap to reason about, and it keeps retry loops from being free)."""
    today = now().date()
    limit = quota_limit(settings, kind)
    budget = settings.ai_global_daily_budget
    try:
        db.execute(
            _insert(db, UsageCounter).values(user_id=user_id, day=today, kind=kind, count=0).on_conflict_do_nothing()
        )
        spent = db.execute(
            update(UsageCounter)
            .where(
                UsageCounter.user_id == user_id,
                UsageCounter.day == today,
                UsageCounter.kind == kind,
                UsageCounter.count < limit,
            )
            .values(count=UsageCounter.count + 1)
        )
        if spent.rowcount != 1:
            raise QuotaExceeded(kind, limit, next_reset(today))
        db.execute(_insert(db, AiBudget).values(day=today, count=0).on_conflict_do_nothing())
        query = update(AiBudget).where(AiBudget.day == today)
        if budget is not None:
            query = query.where(AiBudget.count < budget)
        spent = db.execute(query.values(count=AiBudget.count + 1))
        if spent.rowcount != 1:
            raise QuotaExceeded(kind, budget, next_reset(today), scope="global")
        db.commit()
    except Exception:
        db.rollback()  # A rejected global budget must not consume personal quota.
        raise


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
