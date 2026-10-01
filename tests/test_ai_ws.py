import asyncio
import time

import anthropic
import pytest

from superteacher import ai
from superteacher.routers import ai as router
from tests.ai_fakes import FakeAI, FakeStream, api_error, end_turn, tool_turn


@pytest.fixture
def fake(monkeypatch):
    def install(f):
        monkeypatch.setattr(ai, "client", lambda: f)
        return f

    return install


def drain(ws):
    out = []
    while True:
        ev = ws.receive_json()
        out.append(ev)
        if ev["type"] in ("done", "error"):
            return out


def test_streams_and_history(seeded, fake):
    f = fake(FakeAI([end_turn("Hi ", "there"), end_turn("again")]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "hello"})
        assert [e["type"] for e in drain(ws)] == ["delta", "delta", "done"]
        ws.send_json({"content": "more"})
        drain(ws)
    assert [m["role"] for m in f.stream_calls[1]["messages"]] == ["user", "assistant", "user"]


def test_tool_events_are_opt_in(seeded, fake):
    fake(FakeAI([tool_turn("t", "class_stats", {}), end_turn("a"), tool_turn("t", "class_stats", {}), end_turn("b")]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "q"})
        assert "tool" not in [e["type"] for e in drain(ws)]
        ws.send_json({"content": "q2", "tool_events": True})
        evs = drain(ws)
        assert {"type": "tool", "name": "class_stats"} in evs


def test_upstream_error_is_friendly_and_connection_survives(seeded, fake):
    fake(FakeAI([FakeStream([], "end_turn", [], raises=api_error(anthropic.RateLimitError, 429)), end_turn("ok")]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "q"})
        err = drain(ws)[-1]
        assert err["type"] == "error" and "secret" not in err["message"] and "too many" in err["message"]
        ws.send_json({"content": "q"})
        assert drain(ws)[-1]["type"] == "done"


def test_long_message_and_binary_rejected(seeded, fake):
    f = fake(FakeAI([end_turn("ok")]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "x" * (router.MAX_MESSAGE_CHARS + 1)})
        assert "too long" in ws.receive_json()["message"]
        ws.send_bytes(b"\x00")
        assert "Binary" in ws.receive_json()["message"]
        ws.send_text("[1,2]")
        assert ws.receive_json()["message"] == "Invalid message"
        ws.send_json({"content": "fine"})
        assert drain(ws)[-1]["type"] == "done"
    assert len(f.stream_calls) == 1


def test_rate_limit_per_connection(seeded, fake, monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MIN", "2")
    fake(FakeAI([end_turn("a"), end_turn("b")]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        for _ in range(2):
            ws.send_json({"content": "q"})
            assert drain(ws)[-1]["type"] == "done"
        ws.send_json({"content": "q"})
        assert "too quickly" in ws.receive_json()["message"]


def test_oversized_frame_closes_1009(seeded, fake):
    fake(FakeAI())
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_text("x" * (router.MAX_FRAME_CHARS + 1))
        with pytest.raises(Exception) as ei:
            ws.receive_json()
        assert getattr(ei.value, "code", 1009) == 1009


def test_disconnect_midstream_cancels_upstream(seeded, fake):
    class Hang(FakeStream):
        @property
        def text_stream(self):
            async def gen():
                yield "first"
                await asyncio.sleep(30)

            return gen()

    f = fake(FakeAI([Hang([], "end_turn", [])]))
    with seeded.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "q"})
        assert ws.receive_json()["type"] == "delta"
        ws.close()
        # Wait for the server's disconnect cleanup *inside* the block: leaving it makes Starlette's TestClient cancel
        # the app task right away, which races the cleanup and can surface as a spurious CancelledError.
        deadline = time.time() + 3
        while not f.streams[0].closed and time.time() < deadline:
            time.sleep(0.05)
    assert f.streams[0].closed


def test_rate_limiter_window():
    t = [0.0]
    rl = router.RateLimiter(2, 10, clock=lambda: t[0])
    assert rl.allow() and rl.allow() and not rl.allow()
    t[0] = 10.0
    assert rl.allow()
