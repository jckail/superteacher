"""Gradebook envelopes carry the same school cutoff used by their calculations."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from superteacher import calendar
from superteacher.config import Settings
from superteacher.main import create_app
from superteacher.models import OWNER_ID, Score, Section
from superteacher.routers import gradebook as route


@pytest.fixture
def fixed_gradebook(engine, session_factory, monkeypatch):
    instant = [datetime(2026, 10, 1, 6, 59, tzinfo=UTC)]
    monkeypatch.setattr(calendar, "utc_now", lambda: instant[0])
    settings = Settings(auth_disabled=True, school_timezone="America/Los_Angeles", anthropic_api_key=None)
    app = create_app(session_factory=session_factory, engine=engine, seed=False, settings=settings)
    with TestClient(app) as api:
        course = api.post("/api/courses", json={"name": "Math"}).json()
        section = api.post("/api/sections", json={"course_id": course["id"], "name": "P1"}).json()
        student = api.post("/api/students", json={"name": "Ada", "grade_level": 4, "section_id": section["id"]}).json()
        response = api.post(
            f"/api/sections/{section['id']}/assessments",
            json={"title": "Tomorrow quiz", "kind": "quiz", "max_points": 10, "due_date": "2026-10-01"},
        )
        assert response.status_code == 201
        aid = response.json()["assessments"][0]["id"]
        assert (
            api.put(
                f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": student["id"], "points": 9}]}
            ).status_code
            == 200
        )
        yield api, instant, section, student, aid


def test_gradebook_cutoff_rolls_forward_without_rewriting_future_raw_scores(fixed_gradebook, session_factory):
    api, instant, section, student, aid = fixed_gradebook
    path = f"/api/sections/{section['id']}/gradebook"
    before = api.get(path).json()
    assert before["as_of"] == "2026-09-30"
    assert before["rows"][0]["average"] is None and before["rows"][0]["letter"] is None
    assert before["rows"][0]["points"][aid] == 9
    with session_factory() as db:
        original = [
            (score.id, score.points) for score in db.scalars(select(Score).where(Score.student_id == student["id"]))
        ]
    instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
    after = api.get(path).json()
    assert after["as_of"] == "2026-10-01"
    assert after["rows"][0]["average"] == 90 and after["rows"][0]["letter"] == "A-"
    assert after["rows"][0]["points"][aid] == 9
    with session_factory() as db:
        assert [
            (score.id, score.points) for score in db.scalars(select(Score).where(Score.student_id == student["id"]))
        ] == original


def test_gradebook_builder_passes_one_cutoff_when_clock_changes_during_read(
    fixed_gradebook, session_factory, monkeypatch
):
    _api, instant, section, _student, _aid = fixed_gradebook
    original = route.load_summaries
    captured = []

    def advancing(db, owner_id, **filters):
        captured.append(filters.get("today"))
        instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
        return original(db, owner_id, **filters)

    monkeypatch.setattr(route, "load_summaries", advancing)
    with session_factory() as db, calendar.school_calendar("America/Los_Angeles", freeze_day=False):
        result = route.build_gradebook(db, OWNER_ID, db.get(Section, section["id"]))
    assert captured == [date(2026, 9, 30)]
    assert result.as_of == date(2026, 9, 30)
    assert result.rows[0].average is None


def test_gradebook_mutation_envelopes_include_captured_cutoff(fixed_gradebook):
    api, _instant, section, student, aid = fixed_gradebook
    path = f"/api/sections/{section['id']}/assessments"
    created = api.post(path, json={"title": "Another quiz", "kind": "quiz", "max_points": 10})
    changed = api.patch(f"/api/assessments/{aid}", json={"title": "Edited quiz"})
    scored = api.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": student["id"], "points": 12.5}]})
    removed = api.delete(f"/api/assessments/{aid}")
    for response in (created, changed, scored, removed):
        assert response.status_code in (200, 201)
        assert response.json()["as_of"] == "2026-09-30"
    assert scored.json()["rows"][0]["points"][aid] == 12.5
