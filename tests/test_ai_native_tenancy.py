"""Tenant filtering coexists with bounded AI readers and model-aware cached insights."""

import asyncio
import json

import pytest
from sqlalchemy.orm import sessionmaker

from superteacher import ai, ai_tools, metrics, reports
from superteacher.calendar import school_today
from superteacher.config import get_settings
from superteacher.db import Base
from superteacher.models import Assessment, AssessmentKind, Course, InsightCache, Note, Score, Section, Student, User
from tests.ai_fakes import FakeAI


@pytest.fixture
def classrooms(engine):
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        for owner in ("alice", "bob"):
            user = User(id=owner, email=f"{owner}@example.com")
            course = Course(id=f"c-{owner}", name="Math", owner_id=owner)
            sec = Section(id=f"sec-{owner}", name="P1", course=course)
            student = Student(id=f"s-{owner}", name=f"{owner} canary", grade_level=9, section=sec)
            assessment = Assessment(
                id=f"a-{owner}",
                title="Quiz",
                kind=AssessmentKind.quiz,
                max_points=100,
                due_date=school_today(),
                section=sec,
            )
            db.add(user)
            db.flush()
            db.add_all([student, assessment])
            db.flush()
            db.add_all(
                [
                    Score(student=student, assessment=assessment, points=80),
                    Note(student=student, body=f"PRIVATE-{owner}"),
                ]
            )
        db.commit()
    return factory


@pytest.mark.parametrize(
    "name,args",
    [
        ("find_students", {}),
        ("class_stats", {}),
        ("get_student", {"student_id": "s-alice"}),
    ],
)
def test_scoped_tools_and_foreign_focus_do_not_load_other_classroom(classrooms, name, args):
    with classrooms() as db:
        roster, focus = ai.build_context_parts(db, "s-alice", owner_id="bob")
        assert "bob canary" in roster and "alice canary" not in roster and focus == ""
        result = ai_tools.execute(db, name, args, owner_id="bob")
        assert "alice" not in result and "PRIVATE-alice" not in result
        if name == "class_stats":
            assert json.loads(result)["students"] == 1


def test_foreign_insight_rejected_before_cache_or_provider(classrooms, monkeypatch):
    def forbidden_client():
        pytest.fail("Foreign insight must never allocate a model client")

    monkeypatch.setattr(ai, "client", forbidden_client)
    with classrooms() as db:
        student = db.get(Student, "s-alice")
        db.add(
            InsightCache(
                student_id=student.id,
                fingerprint=metrics.fingerprint(student, metrics.compute(student)),
                model=get_settings().anthropic_insight_model,
                payload={"headline": "PRIVATE-alice"},
            )
        )
        db.commit()
        with pytest.raises(ValueError, match="classroom"):
            asyncio.run(ai.ai_insight(db, student, owner_id="bob"))


def test_cached_insight_is_free_but_new_generation_is_owner_charged(classrooms, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "offline-test-key")
    fake = FakeAI(creates=['{"headline":"Grounded insight"}'])
    monkeypatch.setattr(ai, "client", lambda: fake)
    charges = []
    with classrooms() as db:
        student = db.get(Student, "s-bob")
        first = asyncio.run(ai.ai_insight(db, student, lambda: charges.append("bob"), owner_id="bob"))
        second = asyncio.run(ai.ai_insight(db, student, lambda: charges.append("bob"), owner_id="bob"))
    assert first.source == second.source == "ai" and charges == ["bob"] and len(fake.create_calls) == 1


def test_parent_quota_error_propagates_and_private_notes_stay_excluded(classrooms, monkeypatch):
    from fastapi import HTTPException

    fake = FakeAI(creates=['{"subject":"Update","body":"A factual parent update about the classroom work."}'])
    monkeypatch.setattr(reports, "make_client", lambda: fake)

    def denied():
        raise HTTPException(429, "Daily quota reached")

    with classrooms() as db:
        student = db.get(Student, "s-bob")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(reports.parent_update(student, "warm", before_call=denied))
        assert exc.value.status_code == 429 and not fake.create_calls
        result, source = asyncio.run(reports.parent_update(student, "warm"))
    assert source == "ai" and result.subject == "Update"
    assert "PRIVATE" not in fake.create_calls[0]["messages"][0]["content"]


def test_revoked_websocket_cancels_stream_and_closes_before_further_data(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from superteacher.accounts import CurrentUser
    from superteacher.routers import ai as router

    active = True
    closed_stream = False

    checks = []

    async def valid(ws, user, *, touch=False):
        checks.append(touch)
        return active

    async def stream(*args, owner_id):
        nonlocal closed_stream
        assert owner_id == "bob"
        try:
            yield {"type": "delta", "text": "First chunk"}
            await asyncio.Event().wait()
        finally:
            closed_stream = True

    class Socket:
        def __init__(self):
            self.app = SimpleNamespace(state=SimpleNamespace(session_factory=lambda: nullcontext(None)))
            self.frames = []
            self.closed = None
            self.incoming = asyncio.Queue()
            self.incoming.put_nowait({"type": "websocket.receive", "text": '{"content":"hello"}'})

        async def accept(self):
            pass

        async def receive(self):
            return await self.incoming.get()

        async def send_json(self, payload):
            nonlocal active
            self.frames.append(payload)
            if payload["type"] == "delta":
                active = False  # revoked while the upstream stream remains open

        async def close(self, code, reason=""):
            assert closed_stream
            self.closed = code
            self.incoming.put_nowait({"type": "websocket.disconnect"})

    monkeypatch.setattr(router, "ws_session_active", valid)
    monkeypatch.setattr(router, "settings_of", lambda ws: get_settings())
    monkeypatch.setattr(router, "_charge_chat", lambda *args: None)
    monkeypatch.setattr(ai, "build_context_parts", lambda *args, **kwargs: ("Roster", ""))
    monkeypatch.setattr(ai, "run_chat", stream)

    async def run():
        ws = Socket()
        async with asyncio.timeout(3):
            await router.chat_ws(ws, CurrentUser("bob", "bob@example.com"))
        assert ws.closed == 1008 and ws.frames == [{"type": "delta", "text": "First chunk"}]
        assert checks == [True, False]  # Only a user turn refreshes idle activity; watcher polls are read-only.

    asyncio.run(run())
