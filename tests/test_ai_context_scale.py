"""Chat roster snapshots must not hydrate every student's ORM history."""

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
