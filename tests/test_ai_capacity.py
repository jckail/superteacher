"""Offline regressions for the common provider budget, deadlines and cancellation."""

import asyncio

import pytest
from sqlalchemy import select

from superteacher import ai, ai_capacity, reports
from superteacher.config import get_settings
from superteacher.models import Student
from tests.ai_fakes import FakeAI, FakeStream, end_turn
from tests.test_ai_insight import GOOD


class HangingAI(FakeAI):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.cancelled = False

    async def create(self, **kwargs):
        self.started.set()
        try:
            await self.finish.wait()
            self.creates.append(GOOD)
            return await super().create(**kwargs)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def collect(events):
    return [event async for event in events]


def test_mixed_workloads_share_capacity_and_reject_before_client_creation(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)
    fake = HangingAI()
    monkeypatch.setattr(ai, "client", lambda: fake)
    monkeypatch.setattr(reports, "make_client", lambda: pytest.fail("busy work allocated a client"))
    with seeded.app.state.session_factory() as db:
        students = list(db.scalars(select(Student)))

        async def check():
            job = asyncio.create_task(ai.ai_insight(db, students[0]))
            await fake.started.wait()
            # Duplicate requests join the admitted job; distinct requests do not spawn tasks.
            duplicate = asyncio.create_task(ai.ai_insight(db, students[0]))
            await asyncio.sleep(0)
            other = await asyncio.gather(*(ai.ai_insight(db, student) for student in students[1:]))
            assert all(result.source == "rules" for result in other)
            assert len(ai._inflight) == 1
            assert (await reports.parent_update(students[1], "warm"))[1] == "template"
            with pytest.raises(ai.ChatError, match="busy"):
                await collect(ai.run_chat([], "roster"))
            fake.finish.set()
            assert all(result.source == "ai" for result in await asyncio.gather(job, duplicate))
            assert len(fake.create_calls) == 1 and fake.close_calls == 1
            assert not ai._inflight
            lease = ai_capacity.acquire()
            lease.release()

        asyncio.run(check())


def test_cancelled_insight_waiter_does_not_cancel_remaining_waiter(seeded, monkeypatch):
    fake = HangingAI()
    monkeypatch.setattr(ai, "client", lambda: fake)
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()

        async def check():
            first = asyncio.create_task(ai.ai_insight(db, student))
            await fake.started.wait()
            second = asyncio.create_task(ai.ai_insight(db, student))
            await asyncio.sleep(0)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert not fake.cancelled and fake.close_calls == 0
            fake.finish.set()
            assert (await second).source == "ai"
            assert fake.close_calls == 1 and not ai._inflight

        asyncio.run(check())


def test_final_insight_waiter_cancellation_awaits_cleanup_and_releases_capacity(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)
    fake = HangingAI()
    monkeypatch.setattr(ai, "client", lambda: fake)
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()

        async def check():
            task = asyncio.create_task(ai.ai_insight(db, student))
            await fake.started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert fake.cancelled and fake.close_calls == 1 and not ai._inflight
            lease = ai_capacity.acquire()
            lease.release()

        asyncio.run(check())


def test_insight_total_deadline_includes_retry_backoff(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_insight_timeout_seconds", 0.02)
    from tests.ai_fakes import conn_error

    fake = FakeAI(creates=[conn_error(), GOOD])
    monkeypatch.setattr(ai, "client", lambda: fake)
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()
        result = asyncio.run(ai.ai_insight(db, student))
    assert result.source == "rules"
    assert len(fake.create_calls) == 1 and fake.close_calls == 1 and not ai._inflight


def test_chat_deadline_cancels_stream_and_recovers_capacity(monkeypatch):
    class HangingStream(FakeStream):
        @property
        def text_stream(self):
            async def events():
                yield "partial"
                await asyncio.Event().wait()

            return events()

    monkeypatch.setattr(get_settings(), "ai_chat_timeout_seconds", 0.02)
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)
    stream = HangingStream([], "end_turn", [])
    fake = FakeAI([stream, end_turn("ok")])
    monkeypatch.setattr(ai, "client", lambda: fake)

    async def check():
        with pytest.raises(ai.ChatError, match="too long"):
            await collect(ai.run_chat([], "roster"))
        assert stream.closed and fake.close_calls == 1
        # Recovery verifies admission cleanup, not a second 20ms SDK scheduling benchmark.
        monkeypatch.setattr(get_settings(), "ai_chat_timeout_seconds", 1.0)
        assert (await collect(ai.run_chat([], "roster")))[0]["text"] == "ok"

    asyncio.run(check())


def test_capacity_is_loop_local_and_lease_release_idempotent(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)

    async def check():
        lease = ai_capacity.acquire()
        with pytest.raises(ai_capacity.CapacityError):
            ai_capacity.acquire()
        lease.release()
        lease.release()
        replacement = ai_capacity.acquire()
        replacement.release()

    asyncio.run(check())
    asyncio.run(check())


def test_chat_deadline_spans_all_tool_rounds(monkeypatch):
    from tests.ai_fakes import tool_turn

    class SlowStream(FakeStream):
        @property
        def text_stream(self):
            async def events():
                await asyncio.sleep(0.04)
                yield "checking"

            return events()

    turns = [tool_turn(str(i), "class_stats", {}) for i in range(4)]
    streams = [SlowStream(turn.texts, turn.stop_reason, turn.content) for turn in turns]
    fake = FakeAI(streams)
    monkeypatch.setattr(ai, "client", lambda: fake)
    monkeypatch.setattr(get_settings(), "ai_chat_timeout_seconds", 0.06)

    async def tool(*_args):
        return {"type": "tool_result", "tool_use_id": "0", "content": "ok"}

    monkeypatch.setattr(ai, "_run_tool", tool)
    with pytest.raises(ai.ChatError, match="too long"):
        asyncio.run(collect(ai.run_chat([], "roster", session_factory=lambda: None, owner_id="owner0000000")))
    assert len(fake.stream_calls) == 2
    assert all(stream.closed for stream in fake.streams)
    assert fake.close_calls == 1


def test_client_creation_failure_releases_capacity(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_requests", 1)

    def broken():
        raise RuntimeError("client initialization failed")

    monkeypatch.setattr(ai, "client", broken)

    async def check():
        with pytest.raises(RuntimeError, match="initialization"):
            await collect(ai.run_chat([], "roster"))
        lease = ai_capacity.acquire()
        lease.release()

    asyncio.run(check())
