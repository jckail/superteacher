import asyncio
import contextlib
import json
import logging
import time
import weakref
from collections import deque
from collections.abc import Callable

from fastapi import APIRouter, Depends, Request, WebSocket
from sqlalchemy.orm import Session

from .. import accounts, ai, schemas
from ..accounts import CurrentUser
from ..auth import current_user, settings_of
from ..db import get_db
from .roster import get_student_or_404

router = APIRouter(tags=["ai"])
log = logging.getLogger(__name__)

MAX_HISTORY = 20  # messages kept per connection
MAX_MESSAGE_CHARS = 4000  # one user message
MAX_FRAME_CHARS = 64_000  # raw websocket text frame; larger closes the socket (1009)
MAX_CONCURRENT_TURNS = 8  # model calls in flight across all connections
_turn_limits: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def _turn_limit() -> asyncio.Semaphore:
    """The turn limiter for the running loop. A semaphore binds to the loop that first contends on it, so a
    module-level one breaks as soon as a second loop (tests, multiple workers' reloads) uses it."""
    loop = asyncio.get_running_loop()
    limit = _turn_limits.get(loop)
    if limit is None:
        limit = _turn_limits[loop] = asyncio.Semaphore(MAX_CONCURRENT_TURNS)
    return limit


class RateLimiter:
    """Sliding-window limiter: at most ``limit`` events per ``window`` seconds."""

    def __init__(self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: deque[float] = deque()

    def allow(self) -> bool:
        now = self.clock()
        while self.hits and now - self.hits[0] >= self.window:
            self.hits.popleft()
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True


@router.get("/students/{student_id}/insight", response_model=schemas.Insight)
async def student_insight(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    student = get_student_or_404(db, user.id, student_id)

    def charge() -> None:
        try:
            accounts.consume_quota(db, settings_of(request), user.id, "insight")
        except accounts.QuotaExceeded as e:
            raise accounts.quota_http_error(e) from None

    return await ai.ai_insight(db, student, before_generate=charge)


async def _read(ws: WebSocket, inbox: asyncio.Queue) -> None:
    """Pump frames into a queue so a disconnect is noticed even while a reply is streaming."""
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            await inbox.put(msg.get("text") if msg.get("text") is not None else b"")
    except Exception:
        pass
    await inbox.put(None)


@router.websocket("/chat/ws")
async def chat_ws(ws: WebSocket, user: CurrentUser = Depends(current_user)):
    """Streaming chat.

    Client -> {"content": str, "student_id"?: str, "tool_events"?: bool} | {"type": "reset"}
    Server -> (tool* | delta*)* then done | error. ``tool`` events ({"type":"tool","name"}) are only sent
    when the client opts in with ``tool_events: true``, so older clients keep working.
    """
    await ws.accept()
    history: list[dict] = []
    factory = ws.app.state.session_factory
    settings = settings_of(ws)
    limiter = RateLimiter(ai.setting_int("chat_rate_limit_per_min", 12))
    inbox: asyncio.Queue = asyncio.Queue()
    reader = asyncio.create_task(_read(ws, inbox))
    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            await ws.send_json(payload)

    async def turn(content: str, student_id: str | None, tool_events: bool) -> None:
        history.append({"role": "user", "content": content})
        del history[:-MAX_HISTORY]
        while history and history[0]["role"] != "user":  # API requires a leading user turn
            history.pop(0)
        reply: list[str] = []
        try:
            async with _turn_limit():

                def snapshot():
                    with factory() as db:
                        return ai.build_context_parts(db, user.id, student_id)

                roster, focus = await asyncio.to_thread(snapshot)
                async for ev in ai.run_chat(list(history), roster, focus, factory, owner_id=user.id):
                    if ev["type"] == "delta":
                        reply.append(ev["text"])
                        await send(ev)
                    elif tool_events:
                        await send({"type": "tool", "name": ev["name"]})
            history.append({"role": "assistant", "content": "".join(reply)})
            await send({"type": "done"})
        except asyncio.CancelledError:
            _drop_unanswered(history)
            raise
        except ai.ChatError as e:
            _drop_unanswered(history)
            await send({"type": "error", "message": str(e)})
        except Exception:
            log.exception("chat turn failed")
            _drop_unanswered(history)
            with contextlib.suppress(Exception):  # client already gone
                await send({"type": "error", "message": ai.friendly_error(RuntimeError())})

    running: asyncio.Task | None = None
    getter: asyncio.Task | None = None
    try:
        while True:
            getter = getter or asyncio.create_task(inbox.get())
            await asyncio.wait({getter, *([running] if running else [])}, return_when=asyncio.FIRST_COMPLETED)
            if running and running.done():
                running = None
            if not getter.done():
                continue
            raw, getter = getter.result(), None
            if raw is None:
                break  # client disconnected
            if isinstance(raw, bytes):
                await send({"type": "error", "message": "Binary messages are not supported."})
                continue
            if len(raw) > MAX_FRAME_CHARS:
                await ws.close(code=1009)  # message too big
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = None
            if not isinstance(msg, dict):
                await send({"type": "error", "message": "Invalid message"})
                continue
            if msg.get("type") == "reset":
                if running:
                    await send({"type": "error", "message": "Wait for the current reply to finish."})
                else:
                    history.clear()
                continue
            content = msg.get("content")
            content = content.strip() if isinstance(content, str) else ""
            if not content:
                continue
            if running:
                await send({"type": "error", "message": "Please wait for the current reply to finish."})
            elif len(content) > MAX_MESSAGE_CHARS:
                await send(
                    {"type": "error", "message": f"That message is too long (max {MAX_MESSAGE_CHARS} characters)."}
                )
            elif not limiter.allow():
                await send({"type": "error", "message": "You're sending messages too quickly. Please wait a moment."})
            elif (quota_error := _charge_chat(factory, settings, user.id)) is not None:
                await send(quota_error)
            else:
                sid = msg.get("student_id")
                running = asyncio.create_task(
                    turn(content, sid if isinstance(sid, str) else None, msg.get("tool_events") is True)
                )
    except Exception:
        log.debug("chat connection ended", exc_info=True)
    finally:
        for t in (running, getter, reader):
            if t and not t.done():
                t.cancel()  # cancelling a turn exits the upstream stream context manager
        await asyncio.gather(*(t for t in (running, getter, reader) if t), return_exceptions=True)


def _charge_chat(factory, settings, user_id: str) -> dict | None:
    """Count one chat message against the daily quota; the error frame to send when it is used up."""
    with factory() as db:
        try:
            accounts.consume_quota(db, settings, user_id, "chat")
        except accounts.QuotaExceeded as e:
            return {
                "type": "error",
                "code": "quota_exceeded",
                "message": e.message,
                "resets_at": e.resets_at.isoformat(),
            }
    return None


def _drop_unanswered(history: list[dict]) -> None:
    """Remove a trailing user turn so the next request stays well-formed."""
    if history and history[-1]["role"] == "user":
        history.pop()
