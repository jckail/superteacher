"""CSV streaming must preserve bytes without loading section-wide ORM histories."""

import csv
import io
from datetime import timedelta

import pytest
from sqlalchemy import event

from superteacher import reports
from superteacher.calendar import school_today
from superteacher.models import OWNER_ID, Assessment, AssessmentKind, Course, Score, Section, Student, User
from superteacher.queries import load_students, owned_section


def populate(factory, count=405):
    today = school_today()
    with factory() as db:
        db.add(User(id="foreign", email="foreign@example.test"))
        db.add_all(
            [
                Course(id="owned", owner_id=OWNER_ID, name="Math Ω"),
                Course(id="foreign-c", owner_id="foreign", name="Foreign canary"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Section(id="active", course_id="owned", name="P 1"),
                Section(id="old", course_id="owned", name="Old"),
                Section(id="foreign-s", course_id="foreign-c", name="Canary"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Assessment(
                    id="due",
                    section_id="active",
                    title=' =SUM("Ω",1)',
                    kind=AssessmentKind.test,
                    max_points=30,
                    due_date=today,
                ),
                Assessment(
                    id="null",
                    section_id="active",
                    title="Blank",
                    kind=AssessmentKind.homework,
                    max_points=10,
                    due_date=today,
                ),
                Assessment(
                    id="tie-b",
                    section_id="active",
                    title="Twin",
                    kind=AssessmentKind.quiz,
                    max_points=3,
                    due_date=today,
                ),
                Assessment(
                    id="tie-a",
                    section_id="active",
                    title="Twin",
                    kind=AssessmentKind.quiz,
                    max_points=3,
                    due_date=today,
                ),
                Assessment(
                    id="future",
                    section_id="active",
                    title="Tomorrow",
                    kind=AssessmentKind.project,
                    max_points=20,
                    due_date=today + timedelta(days=1),
                ),
                Assessment(
                    id="old-a",
                    section_id="old",
                    title="Old secret",
                    kind=AssessmentKind.test,
                    max_points=100,
                    due_date=today,
                ),
                Assessment(
                    id="foreign-a",
                    section_id="foreign-s",
                    title="Foreign secret",
                    kind=AssessmentKind.test,
                    max_points=100,
                    due_date=today,
                ),
            ]
        )
        db.flush()
        names = ["\t\uff1dSUM(1)", 'Smith, "Ω"\nnext', "same", "same", "zero", "null"]
        db.add_all(
            [
                Student(
                    id=f"s{i:06}",
                    section_id="active",
                    name=names[i] if i < len(names) else f"Student {i:06}",
                    grade_level=9,
                )
                for i in range(count)
            ]
        )
        db.add_all(
            [
                Student(id=f"f{i:06}", section_id="foreign-s", name=f"Foreign canary {i}", grade_level=9)
                for i in range(count)
            ]
        )
        db.flush()
        for i in range(count):
            sid = f"s{i:06}"
            for aid, pts in [
                ("due", None if i == 5 else 0 if i == 4 else 27.899),
                ("null", None),
                ("tie-b", 1.5),
                ("tie-a", 2),
                ("future", 20),
                ("old-a", 100),
                ("foreign-a", 100),
            ]:
                if i in (0, 4, 5) and aid in ("tie-b", "tie-a"):
                    continue
                db.add(Score(student_id=sid, assessment_id=aid, points=pts))
        db.commit()
    return today


def test_csv_stream_matches_legacy_without_orm_histories(client, session_factory, engine):
    today = populate(session_factory, 2005)
    with session_factory() as db:
        section = owned_section(db, OWNER_ID, "active")
        expected = (
            "\ufeff" + reports.gradebook_csv(section, load_students(db, OWNER_ID, section_id="active"), today)
        ).encode()
    loaded, statements = [], []

    def on_load(session, instance):
        loaded.append(type(instance).__name__)

    def on_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(session_factory.class_, "loaded_as_persistent", on_load)
    event.listen(engine, "before_cursor_execute", on_sql)
    try:
        response = client.get("/api/reports/sections/active/gradebook.csv")
    finally:
        event.remove(session_factory.class_, "loaded_as_persistent", on_load)
        event.remove(engine, "before_cursor_execute", on_sql)
    assert response.status_code == 200
    assert response.content == expected
    assert response.content.count(b"\xef\xbb\xbf") == 1
    assert "content-length" not in response.headers
    assert response.headers["content-disposition"] == 'attachment; filename="gradebook-math-p-1.csv"'
    assert response.headers["cache-control"] == "no-store"
    assert not {"Student", "Score", "AttendanceRecord", "Assessment", "Section", "Course"}.intersection(loaded)
    assert not any("attendance" in sql for sql, _ in statements)
    student_queries = [
        (sql, params) for sql, params in statements if "FROM students JOIN" in sql and "scores" not in sql
    ]
    assert len(student_queries) >= 3
    assert all("LIMIT" in sql for sql, _ in student_queries)
    score_queries = [(sql, params) for sql, params in statements if "FROM scores JOIN" in sql]
    assert len(score_queries) == 11
    assert all("owner_id" in sql and "assessments.section_id" in sql for sql, _ in score_queries)
    assert all(len(params) <= 205 for _, params in score_queries)
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 2006
    assert all(len(row) == 8 for row in rows)
    by_name = {row[0]: row for row in rows[1:]}
    assert by_name["zero"][1:4] == ["0.0", "F", "0"]
    assert by_name["null"][1:4] == ["", "", ""]
    assert by_name["'\t\uff1dSUM(1)"][1:4] == ["93.0", "A-", "27.899"]
    assert not any("secret" in cell or "Foreign canary" in cell for row in rows for cell in row)


def test_foreign_and_missing_sections_fail_before_csv_headers(client, session_factory):
    populate(session_factory, 6)
    for sid in ("foreign-s", "absent"):
        response = client.get(f"/api/reports/sections/{sid}/gradebook.csv")
        assert response.status_code == 404
        assert response.json() == {"detail": "Section not found"}
        assert "content-disposition" not in response.headers


class ResultProbe:
    """Measure actual SQLAlchemy result consumption without changing queries."""

    def __init__(self, result, records):
        self.result = result
        self.records = records
        self.closed = False
        self.sizes = []
        records.append(self)

    def first(self):
        return self.result.first()

    def all(self):
        rows = self.result.all()
        self.sizes.append(len(rows))
        return rows

    def partitions(self, size):
        for rows in self.result.partitions(size):
            self.sizes.append(len(rows))
            yield rows

    def close(self):
        self.result.close()
        self.closed = True


def tracking_factory(factory):
    from sqlalchemy.orm import Session, sessionmaker

    sessions, results = [], []

    class TrackingSession(Session):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.closed = False
            sessions.append(self)

        def execute(self, *args, **kwargs):
            return ResultProbe(super().execute(*args, **kwargs), results)

        def close(self):
            super().close()
            self.closed = True

    return sessionmaker(bind=factory.kw["bind"], class_=TrackingSession), sessions, results


def test_bounded_fetches_chunks_and_session_owned_by_iterator(client, session_factory, monkeypatch):
    from superteacher.gradebook_export import csv_chunks, read_metadata

    today = populate(session_factory)
    with session_factory() as db:
        metadata = read_metadata(db, OWNER_ID, "active")
    tracked, sessions, results = tracking_factory(session_factory)
    # Force rows and even the header to span chunks, including UTF-8 boundaries.
    monkeypatch.setattr("superteacher.gradebook_export.CHUNK_BYTES", 17)
    stream = csv_chunks(tracked, OWNER_ID, "active", metadata, today)
    chunks = list(stream)
    assert max(map(len, chunks)) <= 17
    decoded = b"".join(chunks).decode("utf-8-sig")
    assert len(list(csv.reader(io.StringIO(decoded)))) == 406
    assert all(session.closed and not session.identity_map for session in sessions)
    assert all(result.closed for result in results)
    student_results = results[::2]
    score_results = results[1::2]
    assert max(size for result in student_results for size in result.sizes) <= 200
    assert max(size for result in score_results for size in result.sizes) <= 1000


def test_stream_failure_closes_results_and_session(client, session_factory, monkeypatch):
    import asyncio

    import pytest
    from starlette.responses import StreamingResponse

    from superteacher.gradebook_export import ClosingStreamingResponse, csv_chunks, read_metadata

    today = populate(session_factory, 6)
    with session_factory() as db:
        metadata = read_metadata(db, OWNER_ID, "active")
    tracked, sessions, results = tracking_factory(session_factory)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic metric failure")

    monkeypatch.setattr("superteacher.gradebook_export.metrics.compute_from", fail)
    response = ClosingStreamingResponse(csv_chunks(tracked, OWNER_ID, "active", metadata, today))
    assert isinstance(response, StreamingResponse)
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        await asyncio.Event().wait()

    async def run():
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    with pytest.raises(RuntimeError, match="synthetic metric failure"):
        asyncio.run(run())
    assert messages[0]["status"] == 200
    assert any(m.get("body", b"").startswith(b"\xef\xbb\xbf") for m in messages)
    assert not any(m.get("more_body") is False for m in messages)
    assert sessions and all(session.closed for session in sessions)
    assert results and all(result.closed for result in results)


def test_asgi_disconnect_closes_generator_session(client, session_factory):
    import asyncio

    import pytest
    from starlette.requests import ClientDisconnect

    from superteacher.gradebook_export import ClosingStreamingResponse, csv_chunks, read_metadata

    today = populate(session_factory)
    with session_factory() as db:
        metadata = read_metadata(db, OWNER_ID, "active")

    async def run(spec):
        tracked, sessions, results = tracking_factory(session_factory)
        response = ClosingStreamingResponse(csv_chunks(tracked, OWNER_ID, "active", metadata, today))
        disconnected = asyncio.Event()
        bodies = []

        async def send(message):
            if message["type"] == "http.response.body":
                bodies.append(message)
                if len(bodies) == 2:
                    if spec == "2.4":
                        raise OSError("synthetic socket closed")
                    disconnected.set()
                    await asyncio.Event().wait()

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        if spec == "2.4":
            with pytest.raises(ClientDisconnect):
                await response({"type": "http", "asgi": {"spec_version": spec}}, receive, send)
        else:
            await response({"type": "http", "asgi": {"spec_version": spec}}, receive, send)
        assert len(bodies) == 2  # Header and one student, never a completed download.
        assert all(m["more_body"] is True for m in bodies)
        assert sessions and all(session.closed for session in sessions)
        assert results and all(result.closed for result in results)

    asyncio.run(run("2.0"))
    asyncio.run(run("2.4"))


def test_endpoint_releases_preflight_session_before_stream_headers(client, session_factory):
    import asyncio
    from types import SimpleNamespace

    from fastapi import FastAPI

    from superteacher.auth import current_user
    from superteacher.db import get_db
    from superteacher.routers.reports import router

    populate(session_factory, 6)
    tracked, sessions, results = tracking_factory(session_factory)
    app = FastAPI()
    app.state.session_factory = tracked
    app.include_router(router)

    def db_override():
        with tracked() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=OWNER_ID)
    closed_at_headers = []

    async def send(message):
        if message["type"] == "http.response.start":
            closed_at_headers.extend(session.closed for session in sessions)

    async def receive():
        await asyncio.Event().wait()

    async def run():
        await app(
            {
                "type": "http",
                "asgi": {"spec_version": "2.4"},
                "method": "GET",
                "scheme": "http",
                "path": "/reports/sections/active/gradebook.csv",
                "query_string": b"",
                "headers": [],
                "root_path": "",
                "server": ("test", 80),
                "client": ("test", 1),
            },
            receive,
            send,
        )

    asyncio.run(run())
    assert closed_at_headers == [True]
    assert len(sessions) == 2 and all(session.closed for session in sessions)
    assert all(result.closed for result in results)


def test_score_fetch_error_closes_active_result(client, session_factory, monkeypatch):
    import pytest

    from superteacher.gradebook_export import csv_chunks, read_metadata

    today = populate(session_factory, 6)
    with session_factory() as db:
        metadata = read_metadata(db, OWNER_ID, "active")
    tracked, sessions, results = tracking_factory(session_factory)
    original = ResultProbe.partitions

    def failing_partitions(result, size):
        for rows in original(result, size):
            yield rows
            raise RuntimeError("synthetic score fetch failure")

    monkeypatch.setattr(ResultProbe, "partitions", failing_partitions)
    stream = csv_chunks(tracked, OWNER_ID, "active", metadata, today)
    assert next(stream).startswith(b"\xef\xbb\xbf")
    with pytest.raises(RuntimeError, match="synthetic score fetch failure"):
        next(stream)
    assert sessions and all(session.closed for session in sessions)
    assert results and all(result.closed for result in results)


def test_wide_header_chunks_and_long_transfer_history(client, session_factory):
    from superteacher.gradebook_export import csv_chunks, read_metadata

    today = populate(session_factory, 6)
    with session_factory() as db:
        # Wide output remains width-dependent, while a transferred student's
        # much longer old history must never become part of the active export.
        wide = [
            Assessment(
                id=f"wide{i:04}",
                section_id="active",
                title="Ω" * 120,
                kind=AssessmentKind.test,
                max_points=100,
                due_date=today,
            )
            for i in range(500)
        ]
        old = [
            Assessment(
                id=f"old{i:04}",
                section_id="old",
                title=f"History canary {i}",
                kind=AssessmentKind.test,
                max_points=100,
                due_date=today,
            )
            for i in range(1500)
        ]
        db.add_all(wide + old)
        db.flush()
        db.add_all([Score(student_id="s000000", assessment_id=a.id, points=100) for a in old])
        db.commit()
        metadata = read_metadata(db, OWNER_ID, "active")
        expected = (
            "\ufeff"
            + reports.gradebook_csv(
                owned_section(db, OWNER_ID, "active"),
                load_students(db, OWNER_ID, section_id="active"),
                today,
            )
        ).encode()
    tracked, sessions, results = tracking_factory(session_factory)
    chunks = list(csv_chunks(tracked, OWNER_ID, "active", metadata, today))
    assert max(map(len, chunks)) <= 64 * 1024
    assert b"".join(chunks) == expected
    rows = list(csv.reader(io.StringIO(expected.decode("utf-8-sig"))))
    assert len(rows[0]) == 508
    assert "History canary" not in expected.decode()
    # The score-result partitions contain only active cells, not 1500 old rows.
    assert sum(results[1].sizes) <= 6 * 5
    assert all(session.closed and not session.identity_map for session in sessions)
    assert all(result.closed for result in results)


@pytest.mark.parametrize("cancel_count", [1, 2])
def test_raw_task_cancellation_waits_for_active_next_before_session_close(
    client, session_factory, monkeypatch, cancel_count
):
    import asyncio
    import threading

    import pytest

    from superteacher.gradebook_export import ClosingStreamingResponse, csv_chunks, read_metadata

    today = populate(session_factory, 6)
    with session_factory() as db:
        metadata = read_metadata(db, OWNER_ID, "active")
    tracked, sessions, results = tracking_factory(session_factory)
    entered_next, finish_next = threading.Event(), threading.Event()
    original = reports.metrics.compute_from

    def delayed_metrics(*args, **kwargs):
        entered_next.set()
        assert finish_next.wait(5), "test failed to release the synchronous next worker"
        return original(*args, **kwargs)

    monkeypatch.setattr("superteacher.gradebook_export.metrics.compute_from", delayed_metrics)
    close_calls = []
    stream = csv_chunks(tracked, OWNER_ID, "active", metadata, today)

    class ObservedSource:
        def __iter__(self):
            return self

        def __next__(self):
            return next(stream)

        def close(self):
            close_calls.append(1)
            stream.close()

    response = ClosingStreamingResponse(ObservedSource())
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        await asyncio.Event().wait()

    async def run():
        task = asyncio.create_task(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send))
        try:
            assert await asyncio.to_thread(entered_next.wait, 5)
            assert sessions and not sessions[0].closed
            task.cancel()
            # Give cancellation a chance to enter cleanup while next() is still
            # actively inside a real CSV generator with its session open.
            await asyncio.sleep(0.02)
            assert not task.done(), "response exited before its synchronous next worker finished"
            for _ in range(cancel_count - 1):
                task.cancel()
                await asyncio.sleep(0.02)
                assert not task.done(), "repeated cancellation detached source cleanup"
                assert not sessions[0].closed
        finally:
            finish_next.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert close_calls == [1]
        assert sessions and all(session.closed for session in sessions)
        assert results and all(result.closed for result in results)
        assert not any(message.get("more_body") is False for message in messages)
        assert len([message for message in messages if message["type"] == "http.response.body"]) == 1

    asyncio.run(run())


def test_terminal_cleanup_cancellation_propagates_without_busy_loop():
    import subprocess
    import sys
    import textwrap

    # Isolate the regression: a completed cancelled cleanup task must not make
    # the response spin forever and prevent the event loop's own timeouts.
    script = textwrap.dedent("""
        import asyncio
        from superteacher.gradebook_export import ClosingStreamingResponse

        class Source:
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration
            def close(self):
                raise asyncio.CancelledError("terminal cleanup cancellation")

        async def send(message):
            pass

        async def receive():
            await asyncio.Event().wait()

        async def run():
            response = ClosingStreamingResponse(Source())
            try:
                await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
            except asyncio.CancelledError as exc:
                assert str(exc) == "terminal cleanup cancellation", str(exc)
            else:
                raise AssertionError("terminal cleanup cancellation was swallowed")
            print("cleanup cancellation propagated")

        asyncio.run(run())
    """)
    try:
        process = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail("completed cancelled cleanup task trapped the response in a busy loop")
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "cleanup cancellation propagated"
