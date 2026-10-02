"""Chat roster snapshots must not hydrate every student's ORM history."""

import pytest
from sqlalchemy import event

from superteacher import ai
from superteacher.models import AttendanceRecord, Note, Score


def test_roster_snapshot_reads_column_history_without_orm_hydration(seeded, monkeypatch):
    monkeypatch.setenv("CHAT_ROSTER_CAP", "5")
    loaded = []
    with seeded.app.state.session_factory() as db:
        event.listen(db, "loaded_as_persistent", lambda session, instance: loaded.append(type(instance)))
        roster, focus = ai.build_context_parts(db)
    assert "Roster snapshot (45 students)" in roster
    assert "Large roster" in roster
    assert focus == ""
    assert not {Score, AttendanceRecord, Note}.intersection(loaded)
    # Metadata, section summaries and at most five individual records.
    assert sum("(id " in line for line in roster.splitlines()) <= 5


def test_focus_history_is_scoped_to_one_student_and_recent_work(seeded, monkeypatch):
    student_id = seeded.get("/api/students").json()[0]["id"]
    monkeypatch.setenv("CHAT_ROSTER_CAP", "2")
    loaded_scores = []
    with seeded.app.state.session_factory() as db:

        def record(session, instance):
            if isinstance(instance, Score):
                loaded_scores.append(instance.student_id)

        event.listen(db, "loaded_as_persistent", record)
        _, focus = ai.build_context_parts(db, student_id)
    assert loaded_scores and set(loaded_scores) == {student_id}
    assert "up to 30 recent work records" in focus
    assert focus.count("  · ") <= 30


@pytest.mark.parametrize("cap", [1, 60])
def test_status_metadata_precedes_untrusted_roster_boundary(client, monkeypatch, cap):
    course = client.post("/api/courses", json={"name": "Synthetic course"}).json()
    section = client.post("/api/sections", json={"course_id": course["id"], "name": "Synthetic section"}).json()
    for name in ("First learner", "Second learner"):
        response = client.post("/api/students", json={"name": name, "grade_level": 7, "section_id": section["id"]})
        assert response.status_code == 201
    monkeypatch.setenv("CHAT_ROSTER_CAP", str(cap))
    with client.app.state.session_factory() as db:
        roster, focus = ai.build_context_parts(db)
    trusted, body = roster.split("<roster>\n", 1)
    assert "Status counts: {'unknown': 2, 'on_track': 0, 'watch': 0, 'at_risk': 0}" in trusted
    assert "Unknown means not enough data; only watch/at_risk are attention flags." in trusted
    assert "Status counts:" not in body and "attention flags" not in body
    assert roster.count("<roster>") == roster.count("</roster>") == 1
    assert body.rstrip().endswith("</roster>") and not focus
    if cap == 1:
        assert body.startswith("Large roster:")
        assert "students flagged" not in body and " (id " not in body
    else:
        assert body.startswith("- ") and body.count("status unknown") == 2
