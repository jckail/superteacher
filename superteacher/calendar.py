"""School dates use one explicit IANA timezone; event timestamps remain UTC."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from .config import get_settings

_timezone: ContextVar[str | None] = ContextVar("school_timezone", default=None)
_today: ContextVar[date | None] = ContextVar("school_today", default=None)


def utc_now() -> datetime:
    """Aware UTC clock, also the single seam for deterministic date tests."""
    return datetime.now(UTC)


def school_timezone() -> str:
    return _timezone.get() or get_settings().school_timezone


def school_today() -> date:
    return _today.get() or utc_now().astimezone(ZoneInfo(school_timezone())).date()


@contextmanager
def school_calendar(timezone: str, *, freeze_day: bool = True):
    """Bind one date for an operation; context propagates to async and worker tasks."""
    zone = ZoneInfo(timezone)
    zone_token = _timezone.set(timezone)
    day_token = _today.set(utc_now().astimezone(zone).date() if freeze_day else None)
    try:
        yield
    finally:
        _today.reset(day_token)
        _timezone.reset(zone_token)


class SchoolCalendarMiddleware:
    """Pure ASGI middleware covers both HTTP and websocket connections."""

    def __init__(self, app, timezone: str):
        self.app = app
        self.timezone = timezone

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            with school_calendar(self.timezone, freeze_day=scope["type"] == "http"):
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
