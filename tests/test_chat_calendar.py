"""A chat turn shares one school date across its snapshot and threaded tools."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from superteacher import ai, ai_tools, calendar
from superteacher.config import Settings
from superteacher.main import create_app


def test_turn_crossing_midnight_freezes_tools_and_next_turn_advances(engine, session_factory, monkeypatch):
    instant = [datetime(2026, 10, 1, 6, 59, tzinfo=UTC)]
    monkeypatch.setattr(calendar, "utc_now", lambda: instant[0])
    snapshots = []

    # Exercise the real threaded tool dispatch with a deterministic calendar-only lookup.
    monkeypatch.setattr(ai_tools, "execute", lambda db, name, args: calendar.school_today().isoformat())

    async def run_chat(history, roster, focus, factory):
        snapshots.append(roster.split(".", 1)[0])
        instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
        result = await ai._run_tool(factory, SimpleNamespace(id="calendar", name="class_stats", input={}))
        assert not result.get("is_error")
        yield {"type": "delta", "text": result["content"]}

    monkeypatch.setattr(ai, "run_chat", run_chat)
    app = create_app(
        session_factory,
        engine,
        seed=False,
        settings=Settings(auth_disabled=True, school_timezone="America/Los_Angeles"),
    )
    with TestClient(app) as client, client.websocket_connect("/api/chat/ws") as ws:
        for day in ("2026-09-30", "2026-10-01"):
            ws.send_json({"content": "Check today's class"})
            assert ws.receive_json() == {"type": "delta", "text": day}
            assert ws.receive_json() == {"type": "done"}
    assert snapshots == ["Today is 2026-09-30", "Today is 2026-10-01"]
