"""Synthetic account export completeness, bounded reads and stream ownership."""

import asyncio
import json
import tracemalloc
from datetime import UTC, date, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session, sessionmaker

from superteacher.db import Base
from superteacher.models import (
    Assessment,
    AttendanceRecord,
    AuthSession,
    Course,
    InsightCache,
    LoginToken,
    Note,
    Score,
    Section,
    Student,
    User,
)

STAMP = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)


def populate(engine, history=2, students=2):
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(User),
            [
                {"id": "mine", "email": "mine@example.com", "created_at": STAMP},
                {"id": "foreign", "email": "foreign@example.com", "created_at": STAMP},
            ],
        )
        conn.execute(
            insert(Course),
            [
                {"id": "course", "owner_id": "mine", "name": "Å science 🧪"},
                {"id": "empty", "owner_id": "mine", "name": "Empty"},
                {"id": "foreign", "owner_id": "foreign", "name": "FOREIGN-COURSE"},
            ],
        )
        conn.execute(
            insert(Section),
            [
                {"id": "active", "course_id": "course", "name": "Current"},
                {"id": "old", "course_id": "course", "name": "Previous"},
                {"id": "empty", "course_id": "course", "name": "Empty"},
                {"id": "foreign", "course_id": "foreign", "name": "FOREIGN-SECTION"},
            ],
        )
        conn.execute(
            insert(Student),
            [
                {"id": f"s{i:06}", "section_id": "active", "name": 'Éva "same"', "grade_level": 9}
                for i in range(students)
            ]
            + [{"id": "foreign", "section_id": "foreign", "name": "FOREIGN-STUDENT", "grade_level": 8}],
        )
        conn.execute(
            insert(Assessment),
            [
                {
                    "id": f"a{i:06}",
                    "section_id": "old" if i % 2 else "active",
                    "title": "Same title",
                    "kind": "quiz",
                    "max_points": 10,
                    "due_date": date(2026, 2, 3),
                }
                for i in range(history)
            ]
            + [
                {
                    "id": "foreign",
                    "section_id": "foreign",
                    "title": "FOREIGN-TITLE",
                    "kind": "test",
                    "max_points": 100,
                    "due_date": date(2026, 2, 3),
                }
            ],
        )
        conn.execute(
            insert(Score),
            [
                {
                    "id": f"g{i:06}",
                    "student_id": "s000000",
                    "assessment_id": f"a{i:06}",
                    "points": None if i % 2 else 0.0,
                }
                for i in range(history)
            ]
            + [{"id": "foreign", "student_id": "s000000", "assessment_id": "foreign", "points": 50}],
        )
        conn.execute(
            insert(AttendanceRecord),
            [
                {
                    "id": f"d{i:06}",
                    "student_id": "s000000",
                    "day": date(2020, 1, 1) + timedelta(days=i),
                    "status": "excused" if i % 2 else "present",
                }
                for i in range(history)
            ],
        )
        conn.execute(
            insert(Note),
            [
                {"id": f"n{i:06}", "student_id": "s000000", "body": "私の note\n", "created_at": STAMP}
                for i in range(history)
            ]
            + [{"id": "foreign", "student_id": "foreign", "body": "FOREIGN-NOTE", "created_at": STAMP}],
        )
        conn.execute(
            insert(InsightCache),
            [
                {
                    "student_id": "s000000",
                    "model": "synthetic",
                    "fingerprint": "PRIVATE-FINGERPRINT",
                    "payload": {"headline": "Unicode 🧪", "empty": None},
                    "created_at": STAMP,
                },
                {
                    "student_id": "foreign",
                    "model": "foreign",
                    "fingerprint": "FOREIGN-FINGERPRINT",
                    "payload": {"headline": "FOREIGN-INSIGHT"},
                    "created_at": STAMP,
                },
            ],
        )
        conn.execute(
            insert(AuthSession),
            [
                {
                    "id_hash": "AUTH-SESSION-SECRET",
                    "user_id": "mine",
                    "created_at": STAMP,
                    "expires_at": STAMP + timedelta(days=1),
                }
            ],
        )
        conn.execute(
            insert(LoginToken),
            [{"token_hash": "AUTH-LOGIN-SECRET", "email": "mine@example.com", "expires_at": STAMP + timedelta(days=1)}],
        )


def legacy_reference(factory):
    """Independent old endpoint schema/order oracle, using the old ORM read path."""

    def iso(value):
        return value.isoformat() if value is not None else None

    with factory() as db:
        courses = []
        for course in db.scalars(select(Course).where(Course.owner_id == "mine").order_by(Course.name)):
            sections = []
            for section in db.scalars(select(Section).where(Section.course_id == course.id).order_by(Section.name)):
                assessments = [
                    {
                        "id": a.id,
                        "title": a.title,
                        "kind": a.kind.value,
                        "max_points": a.max_points,
                        "due_date": iso(a.due_date),
                    }
                    for a in db.scalars(
                        select(Assessment)
                        .where(Assessment.section_id == section.id)
                        .order_by(Assessment.due_date, Assessment.title)
                    )
                ]
                students = []
                for st in db.scalars(select(Student).where(Student.section_id == section.id).order_by(Student.name)):
                    insight = db.get(InsightCache, st.id)
                    students.append(
                        {
                            "id": st.id,
                            "name": st.name,
                            "grade_level": st.grade_level,
                            "scores": [
                                {
                                    "id": score.id,
                                    "assessment_id": a.id,
                                    "points": score.points,
                                    "title": a.title,
                                    "kind": a.kind.value,
                                    "max_points": a.max_points,
                                    "due_date": iso(a.due_date),
                                    "section_id": sec.id,
                                    "section": sec.name,
                                    "course_id": co.id,
                                    "course": co.name,
                                }
                                for score, a, sec, co in db.execute(
                                    select(Score, Assessment, Section, Course)
                                    .join(Assessment, Score.assessment_id == Assessment.id)
                                    .join(Section, Assessment.section_id == Section.id)
                                    .join(Course, Section.course_id == Course.id)
                                    .where(Score.student_id == st.id, Course.owner_id == "mine")
                                    .order_by(Assessment.due_date, Assessment.id)
                                )
                            ],
                            "attendance": [
                                {"day": iso(a.day), "status": a.status.value}
                                for a in db.scalars(
                                    select(AttendanceRecord)
                                    .where(AttendanceRecord.student_id == st.id)
                                    .order_by(AttendanceRecord.day)
                                )
                            ],
                            "notes": [
                                {"id": n.id, "body": n.body, "created_at": iso(n.created_at)}
                                for n in db.scalars(
                                    select(Note).where(Note.student_id == st.id).order_by(Note.created_at)
                                )
                            ],
                            "insight": None
                            if insight is None
                            else {
                                "model": insight.model,
                                "payload": insight.payload,
                                "created_at": iso(insight.created_at),
                            },
                        }
                    )
                sections.append(
                    {
                        "id": section.id,
                        "name": section.name,
                        "course_id": course.id,
                        "assessments": assessments,
                        "students": students,
                    }
                )
            courses.append({"id": course.id, "name": course.name, "sections": sections})
        return {
            "exported_at": STAMP.isoformat(),
            "account": {"email": "mine@example.com", "created_at": iso(db.get(User, "mine").created_at)},
            "courses": courses,
        }


def test_stream_matches_legacy_schema_and_ownership(engine, session_factory):
    from superteacher.account_export import account_chunks, read_metadata

    populate(engine)
    expected = legacy_reference(session_factory)
    with session_factory() as db:
        metadata = read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    output = b"".join(account_chunks(session_factory, "mine", metadata))
    assert json.loads(output) == expected
    for canary in (b"FOREIGN", b"PRIVATE-FINGERPRINT", b"AUTH-", b"sessions", b"token_hash", b"disabled"):
        assert canary not in output


class ResultProbe:
    def __init__(self, result, probes):
        self.result = result
        self.closed = False
        self.sizes = []
        probes.append(self)

    def partitions(self, size):
        for rows in self.result.partitions(size):
            self.sizes.append(len(rows))
            yield rows

    def scalar_one_or_none(self):
        return self.result.scalar_one_or_none()

    def close(self):
        self.result.close()
        self.closed = True


def tracking_factory(factory):
    sessions, results, queries = [], [], []

    class TrackingSession(Session):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.closed = False
            sessions.append(self)

        def execute(self, query, *args, **kwargs):
            queries.append(query)
            return ResultProbe(super().execute(query, *args, **kwargs), results)

        def close(self):
            super().close()
            self.closed = True

    return sessionmaker(bind=factory.kw["bind"], class_=TrackingSession), sessions, results, queries


def test_long_histories_bounded_fetch_and_no_orm_graphs(engine, session_factory, monkeypatch):
    from superteacher.account_export import FETCH_ROWS, account_chunks, read_metadata

    populate(engine, history=3005, students=9)
    tracked, sessions, results, queries = tracking_factory(session_factory)
    with tracked() as db:
        metadata = read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    # A large individual insight remains a single record; only emitted bytes are capped.
    with session_factory() as db:
        db.get(InsightCache, "s000000").payload = {"headline": "🧪" * 100_000}
        db.commit()
    stream = account_chunks(tracked, "mine", metadata)
    chunks = list(stream)
    assert max(map(len, chunks)) <= 64 * 1024
    doc = json.loads(b"".join(chunks))
    mine = next(s for c in doc["courses"] for sec in c["sections"] for s in sec["students"] if s["id"] == "s000000")
    assert len(mine["scores"]) == len(mine["notes"]) == len(mine["attendance"]) == 3005
    assert all(result.closed for result in results)
    assert max(size for result in results for size in result.sizes) <= FETCH_ROWS
    assert all(s.closed and not s.identity_map for s in sessions)
    # 1 preflight, courses, sections per course, two queries per section,
    # four leaf queries per student: independent of history length.
    assert len(queries) == 1 + 1 + 2 + 2 * 3 + 4 * 9
    assert all(q.column_descriptions[0].get("type") is not Student for q in queries)


def test_stream_memory_does_not_retain_history(engine, session_factory):
    from superteacher.account_export import account_chunks, read_metadata

    populate(engine, history=4005, students=2)
    with session_factory() as db:
        metadata = read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    # Consume, do not retain output: complete nested lists would retain thousands
    # of score dictionaries; row streaming retains only the current fetch batch.
    tracemalloc.start()
    total = sum(len(chunk) for chunk in account_chunks(session_factory, "mine", metadata))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert total > 1_000_000
    assert peak < 2_000_000


def test_generator_close_releases_nested_results(engine, session_factory, monkeypatch):
    from superteacher.account_export import account_chunks, read_metadata

    populate(engine, history=405)
    tracked, sessions, results, _ = tracking_factory(session_factory)
    with tracked() as db:
        metadata = read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    monkeypatch.setattr("superteacher.account_export.CHUNK_BYTES", 100)
    source = account_chunks(tracked, "mine", metadata)
    for _ in range(20):
        next(source)
    assert not sessions[-1].closed and len(results) > 4
    source.close()
    assert all(s.closed for s in sessions)
    assert all(r.closed for r in results)


def test_empty_account_and_absent_user_created_date(engine, session_factory):
    from superteacher.account_export import account_chunks, read_metadata

    Base.metadata.create_all(engine)
    with session_factory() as db:
        metadata = read_metadata(db, "missing", "missing@example.com", exported_at=STAMP)
    assert json.loads(b"".join(account_chunks(session_factory, "missing", metadata))) == {
        "exported_at": STAMP.isoformat(),
        "account": {"email": "missing@example.com", "created_at": None},
        "courses": [],
    }


def test_serialization_failure_releases_active_results(engine, session_factory, monkeypatch):
    from superteacher import account_export

    populate(engine, history=405)
    tracked, sessions, results, _ = tracking_factory(session_factory)
    with tracked() as db:
        metadata = account_export.read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    original = account_export._json

    def fail(value):
        if isinstance(value, dict) and "points" in value:
            raise RuntimeError("synthetic score serialization failure")
        return original(value)

    monkeypatch.setattr(account_export, "_json", fail)
    with pytest.raises(RuntimeError, match="synthetic score serialization failure"):
        list(account_export.account_chunks(tracked, "mine", metadata))
    assert all(s.closed for s in sessions)
    assert all(r.closed for r in results)


def test_endpoint_preflight_closed_before_headers(engine, session_factory):
    from types import SimpleNamespace

    from fastapi import FastAPI

    from superteacher.auth import current_user
    from superteacher.db import get_db
    from superteacher.routers.account import router

    populate(engine)
    tracked, sessions, results, _ = tracking_factory(session_factory)
    app = FastAPI()
    app.state.session_factory = tracked
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id="mine", email="mine@example.com")

    def forbidden_dependency():
        pytest.fail("export cannot keep the request DB dependency open")

    app.dependency_overrides[get_db] = forbidden_dependency
    at_headers = []
    bodies = []

    async def send(message):
        if message["type"] == "http.response.start":
            at_headers.extend(s.closed for s in sessions)
        elif message["type"] == "http.response.body":
            bodies.append(message["body"])

    async def receive():
        await asyncio.Event().wait()

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"spec_version": "2.4"},
                "method": "GET",
                "scheme": "http",
                "path": "/account/export",
                "query_string": b"",
                "headers": [],
                "root_path": "",
                "server": ("test", 80),
                "client": ("test", 1),
            },
            receive,
            send,
        )
    )
    assert at_headers == [True]
    assert len(sessions) == 2 and all(s.closed for s in sessions)
    assert all(r.closed for r in results)
    assert json.loads(b"".join(bodies))["account"]["email"] == "mine@example.com"


@pytest.mark.parametrize("mode", ["send_error", "disconnect", "cancel", "generation_error"])
def test_asgi_failure_and_disconnect_close_account_source(engine, session_factory, monkeypatch, mode):
    from starlette.requests import ClientDisconnect

    from superteacher import account_export
    from superteacher.gradebook_export import ClosingStreamingResponse

    populate(engine, history=405)
    tracked, sessions, results, _ = tracking_factory(session_factory)
    with tracked() as db:
        metadata = account_export.read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    monkeypatch.setattr(account_export, "CHUNK_BYTES", 100)
    if mode == "generation_error":
        original = account_export._json

        def fail(value):
            if isinstance(value, dict) and "points" in value:
                raise RuntimeError("synthetic serialization failure")
            return original(value)

        monkeypatch.setattr(account_export, "_json", fail)
    response = ClosingStreamingResponse(account_export.account_chunks(tracked, "mine", metadata))
    messages = []

    async def run():
        body_sent = asyncio.Event()

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body":
                body_sent.set()
                if mode == "send_error":
                    raise OSError("synthetic client disconnect")
                if mode in ("disconnect", "cancel"):
                    await asyncio.Event().wait()

        async def receive():
            await body_sent.wait()
            return {"type": "http.disconnect"}

        scope = {"type": "http", "asgi": {"spec_version": "2.3" if mode == "disconnect" else "2.4"}}
        if mode == "cancel":
            task = asyncio.create_task(response(scope, receive, send))
            await body_sent.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await response(scope, receive, send)

    if mode == "send_error":
        with pytest.raises(ClientDisconnect):
            asyncio.run(run())
    elif mode == "generation_error":
        with pytest.raises(RuntimeError, match="synthetic serialization failure"):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert messages[0]["status"] == 200
    assert not any(m.get("more_body") is False for m in messages)
    assert len(sessions) == 2 and all(s.closed for s in sessions)
    assert results and all(r.closed for r in results)


def test_cancellation_during_account_serialization_waits_for_worker_cleanup(engine, session_factory, monkeypatch):
    from superteacher import account_export
    from superteacher.gradebook_export import ClosingStreamingResponse

    populate(engine, history=405)
    tracked, sessions, results, _ = tracking_factory(session_factory)
    with tracked() as db:
        metadata = account_export.read_metadata(db, "mine", "mine@example.com", exported_at=STAMP)
    entered, release = Event(), Event()
    original = account_export._json

    def blocked(value):
        if isinstance(value, dict) and "points" in value:
            entered.set()
            assert release.wait(5), "test must release active account worker"
        return original(value)

    monkeypatch.setattr(account_export, "_json", blocked)
    monkeypatch.setattr(account_export, "CHUNK_BYTES", 100)
    response = ClosingStreamingResponse(account_export.account_chunks(tracked, "mine", metadata))

    async def run():
        async def send(message):
            pass

        async def receive():
            await asyncio.Event().wait()

        task = asyncio.create_task(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done() and not sessions[-1].closed
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(run())
    assert all(s.closed for s in sessions)
    assert all(r.closed for r in results)
