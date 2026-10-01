import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from .. import ai, schemas
from ..db import get_db
from .roster import get_student_or_404

router = APIRouter(tags=["ai"])
log = logging.getLogger(__name__)
MAX_HISTORY = 20  # messages kept per connection


@router.get("/students/{student_id}/insight", response_model=schemas.Insight)
async def student_insight(student_id: str, db: Session = Depends(get_db)):
    return await ai.ai_insight(db, get_student_or_404(db, student_id))


@router.websocket("/chat/ws")
async def chat_ws(ws: WebSocket):
    """Streaming chat. Client → {"content": str, "student_id"?: str}; server → delta* then done | error."""
    await ws.accept()
    history: list[dict] = []
    factory = ws.app.state.session_factory
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid message"})
                continue
            if msg.get("type") == "reset":
                history.clear()
                continue
            content = (msg.get("content") or "").strip()
            if not content:
                continue

            def snapshot(student_id=msg.get("student_id")):
                with factory() as db:
                    return ai.build_context(db, student_id)

            history.append({"role": "user", "content": content})
            del history[:-MAX_HISTORY]
            while history and history[0]["role"] != "user":  # API requires a leading user turn
                history.pop(0)
            reply = []
            try:
                context = await asyncio.to_thread(snapshot)
                async for chunk in ai.stream_chat(history, context):
                    reply.append(chunk)
                    await ws.send_json({"type": "delta", "text": chunk})
                history.append({"role": "assistant", "content": "".join(reply)})
                await ws.send_json({"type": "done"})
            except WebSocketDisconnect:
                raise
            except Exception:  # noqa: BLE001
                log.exception("chat turn failed")
                history.pop()  # drop the unanswered user turn so the next one stays well-formed
                await ws.send_json({"type": "error", "message": "The assistant hit a problem. Please try again."})
    except WebSocketDisconnect:
        return
