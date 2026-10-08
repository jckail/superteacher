"""Public demo admission through the real WebSocket and SDK Runner boundaries."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from superteacher import ai
from superteacher.config import Settings, get_settings
from superteacher.main import create_app
from tests.ai_fakes import FakeAI, end_turn


def drain(ws):
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] in ("done", "error"):
            return events


def test_five_turns_survive_reset_reconnect_cookie_clear_and_app_restart(engine, session_factory, monkeypatch):
    settings = Settings(
        auth_disabled=False, public_demo=True, session_secret="synthetic-demo-test", cors_origins=["http://testserver"]
    )
    fake = FakeAI([end_turn("Synthetic answer") for _ in range(5)])
    monkeypatch.setattr(ai, "client", lambda: fake)
    monkeypatch.setattr(get_settings(), "public_demo", True)
    app = create_app(settings=settings, engine=engine, session_factory=session_factory, seed=False)
    headers = {"Origin": "http://testserver", "X-Requested-With": "test"}
    with TestClient(app, headers=headers) as client:
        assert client.get("/api/overview").status_code == 200
        assert client.post("/api/demo/session").json()["remaining"] == 5
        for turn in range(5):
            with client.websocket_connect("/api/chat/ws") as ws:
                assert ws.receive_json()["type"] == "quota"
                ws.send_json({"type": "reset"})
                ws.send_json({"content": "Synthetic question"})
                events = drain(ws)
                assert events[-1]["type"] == "done"
                assert next(e for e in events if e["type"] == "quota")["remaining"] == 4 - turn
        with client.websocket_connect("/api/chat/ws") as ws:
            assert ws.receive_json()["remaining"] == 0
            ws.send_json({"content": "Sixth request"})
            assert drain(ws)[-1]["code"] == "quota_exceeded"
        client.cookies.clear()
        assert client.post("/api/demo/session").json()["remaining"] == 0
    restarted = create_app(settings=settings, engine=engine, session_factory=session_factory, seed=False)
    with TestClient(restarted, headers=headers) as client:
        assert client.post("/api/demo/session").json()["remaining"] == 0
        with client.websocket_connect("/api/chat/ws") as ws:
            ws.receive_json()
            ws.send_json({"content": "Restart bypass"})
            assert drain(ws)[-1]["code"] == "quota_exceeded"
    assert len(fake.stream_calls) == 5
    assert all(call["max_tokens"] == 1024 for call in fake.stream_calls)


def test_public_demo_nonchat_features_do_not_call_provider(engine, session_factory, monkeypatch):
    settings = Settings(
        auth_disabled=False, public_demo=True, session_secret="synthetic-demo-test", cors_origins=["http://testserver"]
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Public demo bypassed assistant budget")

    monkeypatch.setattr(ai, "client", forbidden)
    with TestClient(
        create_app(settings=settings, engine=engine, session_factory=session_factory, seed=True),
        headers={"Origin": "http://testserver", "X-Requested-With": "test"},
    ) as client:
        students = client.get("/api/students").json()
        student = students[0]
        insight = client.get("/api/students/" + student["id"] + "/insight")
        assert insight.status_code == 200 and insight.json()["source"] == "rules"
        draft = client.post("/api/reports/students/" + student["id"] + "/parent-update", json={"tone": "warm"})
        assert draft.status_code == 200 and draft.json()["source"] == "template"


@pytest.mark.parametrize("failure", ["disconnect", "quota_snapshot"])
def test_initial_quota_failure_drains_reader_and_watcher(session_factory, monkeypatch, failure):
    """Failure before message admission must leave no connection tasks behind."""
    from types import SimpleNamespace

    from starlette.websockets import WebSocketDisconnect

    from superteacher.routers import ai as router

    config = Settings(auth_disabled=False, public_demo=True, session_secret="synthetic-demo-test")
    monkeypatch.setattr(router, "settings_of", lambda ws: config)
    monkeypatch.setattr(router.demo, "subjects", lambda ws: ("visitor", "network"))

    def quota_status(*args):
        if failure == "quota_snapshot":
            raise RuntimeError("synthetic quota database failure")
        return {"used": 0, "limit": 5, "remaining": 5, "resets_at": "2026-10-08T00:00:00+00:00"}

    monkeypatch.setattr(router.demo, "quota_status", quota_status)
    monkeypatch.setattr(ai, "client", lambda: pytest.fail("Initial quota failure must not call the provider"))
    tasks = {}
    create_task = asyncio.create_task

    def track(coro, *args, **kwargs):
        task = create_task(coro, *args, **kwargs)
        tasks[coro.__name__] = task
        return task

    monkeypatch.setattr(router.asyncio, "create_task", track)

    class Connection:
        app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))
        accepted = False

        def __init__(self):
            self.sent = []

        async def accept(self):
            self.accepted = True

        async def receive(self):
            await asyncio.Event().wait()

        async def send_json(self, payload):
            self.sent.append(payload)
            assert payload["type"] == "quota"
            raise WebSocketDisconnect(code=1000)

    async def check():
        ws = Connection()
        await asyncio.wait_for(router.chat_ws(ws, SimpleNamespace(id="synthetic-owner")), timeout=1)
        assert ws.accepted
        assert set(tasks) == {"_read", "watch_session"}
        assert all(task.done() and task.cancelled() for task in tasks.values())
        assert len(ws.sent) == (1 if failure == "disconnect" else 0)

    asyncio.run(check())
