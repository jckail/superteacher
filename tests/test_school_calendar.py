"""Date boundaries are independent of server/browser timezone and app instance."""

import asyncio
from datetime import UTC, date, datetime

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from pydantic import ValidationError

from superteacher import ai, calendar, metrics, queries, reports, schemas
from superteacher.accounts import ensure_owner
from superteacher.ai_tools import student_block
from superteacher.config import Settings
from superteacher.db import Base
from superteacher.main import create_app
from superteacher.models import (
    Assessment,
    AssessmentKind,
    AttendanceRecord,
    AttendanceStatus,
    Course,
    Score,
    Section,
    Student,
)


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-10-01T00:30:00+00:00", "2026-09-30"),
        ("2026-03-08T09:59:00+00:00", "2026-03-08"),
        ("2026-03-08T10:01:00+00:00", "2026-03-08"),
        ("2026-11-01T08:59:00+00:00", "2026-11-01"),
        ("2026-11-01T09:01:00+00:00", "2026-11-01"),
        ("2026-03-09T06:59:00+00:00", "2026-03-08"),
        ("2026-03-09T07:01:00+00:00", "2026-03-09"),
    ],
)
def test_zoned_date_and_dst(monkeypatch, instant, expected):
    monkeypatch.setattr(calendar, "utc_now", lambda: datetime.fromisoformat(instant))
    with calendar.school_calendar("America/Los_Angeles"):
        assert calendar.school_today().isoformat() == expected


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings(school_timezone="School/Imaginary")


@pytest.mark.parametrize("scope_type,second_day", [("http", date(2026, 9, 30)), ("websocket", date(2026, 10, 1))])
def test_request_date_is_stable_and_long_lived_socket_advances(monkeypatch, scope_type, second_day):
    instant = [datetime(2026, 10, 1, 6, 59, tzinfo=UTC)]
    monkeypatch.setattr(calendar, "utc_now", lambda: instant[0])
    seen = []

    async def application(scope, receive, send):
        seen.append(calendar.school_today())
        instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
        seen.append(await asyncio.to_thread(calendar.school_today))

    middleware = calendar.SchoolCalendarMiddleware(application, "America/Los_Angeles")
    asyncio.run(middleware({"type": scope_type}, None, None))
    assert seen == [date(2026, 9, 30), second_day]


def test_app_injected_timezone_isolated_for_http_websocket_and_threads(engine, session_factory, monkeypatch):
    monkeypatch.setattr(calendar, "utc_now", lambda: datetime(2026, 10, 1, 0, 30, tzinfo=UTC))

    def app(zone):
        instance = create_app(
            session_factory,
            engine,
            seed=False,
            settings=Settings(auth_disabled=True, school_timezone=zone, static_dir="/nonexistent-static-dir"),
        )

        @instance.get("/thread-date")
        async def thread_date():
            return {"today": await asyncio.to_thread(calendar.school_today)}

        @instance.websocket("/socket-date")
        async def socket_date(ws: WebSocket):
            await ws.accept()
            await ws.send_json({"today": (await asyncio.to_thread(calendar.school_today)).isoformat()})
            await ws.close()

        return instance

    with TestClient(app("UTC")) as utc, TestClient(app("America/Los_Angeles")) as local:
        for client, zone, day in (
            (local, "America/Los_Angeles", "2026-09-30"),
            (utc, "UTC", "2026-10-01"),
            (local, "America/Los_Angeles", "2026-09-30"),
        ):
            assert client.get("/api/calendar").json() == {"timezone": zone, "today": day}
            assert client.get("/thread-date").json() == {"today": day}
            with client.websocket_connect("/socket-date") as ws:
                assert ws.receive_json() == {"today": day}


def test_calendar_requires_authentication(engine, session_factory):
    instance = create_app(
        session_factory,
        engine,
        seed=False,
        settings=Settings(auth_disabled=False, auth_password="calendar-pass", session_secret="calendar-secret"),
    )
    with TestClient(instance) as client:
        assert client.get("/api/calendar").status_code == 401


def test_future_work_and_attendance_use_same_date_and_historical_override(engine, session_factory, monkeypatch):
    monkeypatch.setattr(calendar, "utc_now", lambda: datetime(2026, 10, 1, 0, 30, tzinfo=UTC))
    Base.metadata.create_all(engine)
    with session_factory() as db:
        course = Course(name="Algebra", owner_id=ensure_owner(db))
        section = Section(name="Period 1", course=course)
        student = Student(name="Ada", grade_level=9, section=section)
        for title, due, points in (("Past", date(2026, 9, 30), 80), ("Future", date(2026, 10, 1), None)):
            assessment = Assessment(
                title=title, kind=AssessmentKind.homework, due_date=due, max_points=100, section=section
            )
            student.scores.append(Score(assessment=assessment, points=points))
        student.attendance.extend(
            [
                AttendanceRecord(day=date(2026, 9, 30), status=AttendanceStatus.present),
                AttendanceRecord(day=date(2026, 10, 1), status=AttendanceStatus.absent),
            ]
        )
        db.add(student)
        db.commit()
        with calendar.school_calendar("America/Los_Angeles"):
            m = metrics.compute(student)
            assert (m.as_of, m.average, m.missing, m.attendance_rate) == (date(2026, 9, 30), 80, 0, 100)
            assert "NOT YET DUE" in student_block(student, m)
            assert "NOT YET DUE" in reports._context(student, m)
            roster_context, focus = ai.build_context_parts(db, student.id)
            assert "Today is 2026-09-30" in roster_context
            assert "NOT YET DUE" in focus
            assert queries.load_summaries(db)[0][1] == m
            summary = reports.class_summary(section, [student])
            assert summary.as_of == m.as_of
            assert summary.assessments[1].missing_pct is None
            assert len(summary.attendance) == 1
            assert schemas.AttendanceIn(marks=[]).day == m.as_of
            assert schemas.AssessmentIn(title="New").due_date == m.as_of
            direct = Assessment(title="Direct insertion", section=section)
            db.add(direct)
            db.flush()
            assert direct.due_date == m.as_of
            historical = metrics.compute(student, date(2026, 10, 1))
            assert (historical.missing, historical.attendance_rate) == (1, 50)
            assert "MISSING" in student_block(student, historical)
            assert "NOT YET DUE" not in student_block(student, historical)
            assert queries.load_summaries(db, today=date(2026, 10, 1))[0][1] == historical
            assert reports.class_summary(section, [student], date(2026, 10, 1)).as_of == date(2026, 10, 1)
