"""Anonymous public-demo identity and durable admission budgets.

Visitor cookies allocate no database rows. Only admitted AI turns create counters;
failed upstream calls remain charged. Network counters prevent clearing cookies
from creating another allowance. Client address trust follows the ingress policy.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadData
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from . import accounts
from .auth import AuthState, _csrf, _secure, current_user
from .client_address import rate_limit_client
from .config import Settings
from .db import get_db
from .models import AiBudget, DemoUsageCounter

COOKIE = "st_demo_visitor"
COOKIE_TTL = 24 * 3600
router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(current_user)])


def visitor_subject(st: AuthState, cookie: str | None) -> str | None:
    """Verify signed visitor identity; never accept arbitrary browser identifiers."""
    if not isinstance(cookie, str) or not 1 <= len(cookie) <= 512:
        return None
    try:
        payload = st.demo_serializer.loads(cookie, max_age=COOKIE_TTL)
    except BadData:
        return None
    if not (
        type(payload) is dict
        and set(payload) == {"v", "nonce"}
        and type(payload["v"]) is int
        and payload["v"] == 1
        and accounts.opaque_session(payload["nonce"])
    ):
        return None
    return hashlib.sha256(("visitor:" + payload["nonce"]).encode()).hexdigest()


def network_subject(conn: HTTPConnection, st: AuthState) -> str:
    client = rate_limit_client(conn, trusted_hops=st.settings.auth_forwarded_for_trusted_hops)
    return hmac.new(st.key, ("demo-network:" + client).encode(), hashlib.sha256).hexdigest()


def subjects(conn: HTTPConnection) -> tuple[str, str]:
    """Resolve an HTTP or WebSocket's signed cookie and trusted network identity."""
    st = conn.app.state.auth
    visitor = visitor_subject(st, conn.cookies.get(COOKIE))
    if visitor is None:
        raise HTTPException(401, "Start a demo session before using the assistant.")
    return visitor, network_subject(conn, st)


def global_limit(settings: Settings) -> int:
    return settings.ai_global_daily_budget if settings.ai_global_daily_budget is not None else 50


def quota_status(db: Session, settings: Settings, visitor: str, network: str) -> dict:
    today = accounts.now().date()
    rows = db.execute(
        select(DemoUsageCounter.count).where(
            DemoUsageCounter.day == today,
            DemoUsageCounter.kind == "chat",
            DemoUsageCounter.subject.in_((visitor, network)),
        )
    ).scalars()
    limit = settings.public_demo_chat_per_day
    used = min(limit, max(rows, default=0))
    spent = db.scalar(select(AiBudget.count).where(AiBudget.day == today)) or 0
    return {
        "used": used,
        "limit": limit,
        "remaining": min(max(0, limit - used), max(0, global_limit(settings) - spent)),
        "resets_at": accounts.next_reset(today).isoformat(),
    }


def consume_chat(db: Session, settings: Settings, visitor: str, network: str) -> dict:
    """Atomically reserve both daily allowances and the shared global budget.

    Conditional updates hold the DB write lock until commit. Any rejected counter
    rolls back the entire reservation; multiple workers cannot overspend.
    Caller supplies verified subjects and invokes this once before provider work.
    """
    today = accounts.now().date()
    limit = settings.public_demo_chat_per_day
    try:
        # Retention is bounded; issuing cookies and reading status create no rows.
        db.execute(delete(DemoUsageCounter).where(DemoUsageCounter.day < today - timedelta(days=7)))
        for subject in (visitor, network):
            db.execute(
                accounts._insert(db, DemoUsageCounter)
                .values(subject=subject, day=today, kind="chat", count=0)
                .on_conflict_do_nothing()
            )
            result = db.execute(
                update(DemoUsageCounter)
                .where(
                    DemoUsageCounter.subject == subject,
                    DemoUsageCounter.day == today,
                    DemoUsageCounter.kind == "chat",
                    DemoUsageCounter.count < limit,
                )
                .values(count=DemoUsageCounter.count + 1)
            )
            if result.rowcount != 1:
                raise accounts.QuotaExceeded("chat", limit, accounts.next_reset(today))
        budget = global_limit(settings)
        db.execute(accounts._insert(db, AiBudget).values(day=today, count=0).on_conflict_do_nothing())
        result = db.execute(
            update(AiBudget).where(AiBudget.day == today, AiBudget.count < budget).values(count=AiBudget.count + 1)
        )
        if result.rowcount != 1:
            raise accounts.QuotaExceeded("chat", budget, accounts.next_reset(today), scope="global")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return quota_status(db, settings, visitor, network)


def _enabled(request: Request) -> AuthState:
    st = request.app.state.auth
    if not st.public_demo:
        raise HTTPException(404, "Not Found")
    return st


@router.post("/session")
def session(request: Request, response: Response, db: Session = Depends(get_db)):
    st = _enabled(request)
    _csrf(request, st)
    cookie = request.cookies.get(COOKIE)
    visitor = visitor_subject(st, cookie)
    if visitor is None:
        cookie = st.demo_serializer.dumps({"v": 1, "nonce": secrets.token_urlsafe(32)})
        visitor = visitor_subject(st, cookie)
    response.set_cookie(
        COOKIE, cookie, max_age=COOKIE_TTL, httponly=True, secure=_secure(request, st), samesite="lax", path="/"
    )
    response.headers["Cache-Control"] = "no-store"
    return quota_status(db, st.settings, visitor, network_subject(request, st))


@router.get("/status")
def status(request: Request, response: Response, db: Session = Depends(get_db)):
    st = _enabled(request)
    visitor, network = subjects(request)
    response.headers["Cache-Control"] = "no-store"
    return quota_status(db, st.settings, visitor, network)
