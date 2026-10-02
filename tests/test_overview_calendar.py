"""Overview date provenance agrees with its native school-day calculations."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from superteacher import calendar
from superteacher.accounts import CurrentUser
from superteacher.models import OWNER_ID, Score
from superteacher.routers import system
from tests.test_gradebook_calendar import fixed_gradebook as fixed_gradebook


def test_overview_cutoff_rolls_forward_without_rewriting_raw_scores(fixed_gradebook, session_factory):
    api, instant, section, student, aid = fixed_gradebook
    path = f"/api/overview?section_id={section['id']}"
    before = api.get(path).json()
    assert before["as_of"] == "2026-09-30"
    assert before["average"] is None and before["unknown"] == 1
    assert before["distribution"] == dict.fromkeys("ABCDF", 0)
    with session_factory() as db:
        original = [(s.id, s.points) for s in db.scalars(select(Score).where(Score.student_id == student["id"]))]
    instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
    after = api.get(path).json()
    assert after["as_of"] == "2026-10-01"
    assert after["average"] == 90 and after["on_track"] == 1 and after["unknown"] == 0
    assert after["distribution"] == {"A": 1, "B": 0, "C": 0, "D": 0, "F": 0}
    with session_factory() as db:
        assert [
            (s.id, s.points) for s in db.scalars(select(Score).where(Score.student_id == student["id"]))
        ] == original
        assert db.scalar(select(Score.points).where(Score.assessment_id == aid)) == 9


def test_overview_passes_captured_cutoff_even_if_clock_advances_during_iteration(
    fixed_gradebook, session_factory, monkeypatch
):
    _api, instant, section, _student, _aid = fixed_gradebook
    original = system.iter_summaries
    seen = []

    def advancing(db, owner_id, **filters):
        seen.append(filters.get("today"))
        instant[0] = datetime(2026, 10, 1, 7, 1, tzinfo=UTC)
        yield from original(db, owner_id, **filters)

    monkeypatch.setattr(system, "iter_summaries", advancing)
    with session_factory() as db, calendar.school_calendar("America/Los_Angeles", freeze_day=False):
        result = system.overview(db=db, user=CurrentUser(OWNER_ID, None), section_id=section["id"], course_id=None)
    assert seen == [date(2026, 9, 30)]
    assert result.as_of == date(2026, 9, 30)
    assert result.average is None and result.unknown == 1


def test_empty_filtered_overview_still_carries_the_captured_date(fixed_gradebook):
    api, _instant, _section, _student, _aid = fixed_gradebook
    result = api.get("/api/overview?section_id=missing").json()
    assert result == {
        "as_of": "2026-09-30",
        "students": 0,
        "average": None,
        "attendance_rate": None,
        "homework_rate": None,
        "at_risk": 0,
        "watch": 0,
        "on_track": 0,
        "unknown": 0,
        "distribution": dict.fromkeys("ABCDF", 0),
        "attention": [],
    }
