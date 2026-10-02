"""Section changes preserve grades and expose prior-section raw history explicitly."""

import pytest
from sqlalchemy import select

from superteacher.ai_tools import execute
from superteacher.models import Score
from tests.test_backend_audit import mk_assessment


def classroom(client):
    courses = [client.post("/api/courses", json={"name": name}).json() for name in ("Before course", "After course")]
    sections = [
        client.post("/api/sections", json={"name": name, "course_id": course["id"]}).json()
        for name, course in zip(("Before", "After"), courses, strict=True)
    ]
    student = client.post(
        "/api/students", json={"name": "Student", "grade_level": 9, "section_id": sections[0]["id"]}
    ).json()
    assessment = mk_assessment(client, sections[0], title="Original quiz", kind="quiz", mx=100)
    return sections, student, assessment


@pytest.mark.parametrize("original_points", [0, 87])
def test_transfer_preserves_grades_active_metrics_and_moveback(client, session_factory, original_points):
    sections, student, original = classroom(client)
    old_missing = mk_assessment(client, sections[0], title="Original missing homework")
    new_quiz = mk_assessment(client, sections[1], title="New quiz", kind="quiz", mx=100)
    new_missing = mk_assessment(client, sections[1], title="New missing homework")
    client.put(
        f"/api/assessments/{original}/scores",
        json={"scores": [{"student_id": student["id"], "points": original_points}]},
    )
    client.post(f"/api/students/{student['id']}/notes", json={"body": "Keep this note"})
    client.put(
        f"/api/sections/{sections[0]['id']}/attendance",
        json={"marks": [{"student_id": student["id"], "status": "present"}]},
    )
    with session_factory() as db:
        original_rows = {
            sc.assessment_id: (sc.id, sc.points)
            for sc in db.scalars(select(Score).where(Score.student_id == student["id"]))
        }
    moved = client.patch(
        f"/api/students/{student['id']}", json={"section_id": sections[1]["id"], "name": "Changed name"}
    )
    assert moved.status_code == 200
    active = moved.json()
    assert active["name"] == "Changed name"
    assert active["average"] is None and active["missing"] == 2
    assert {p["assessment_id"] for p in active["scores"]} == {new_quiz, new_missing}
    assert active["attendance_rate"] == 100 and active["notes"][0]["body"] == "Keep this note"
    with session_factory() as db:
        rows = {
            sc.assessment_id: (sc.id, sc.points)
            for sc in db.scalars(select(Score).where(Score.student_id == student["id"]))
        }
        assert {aid: rows[aid] for aid in original_rows} == original_rows
        assert len(rows) == 4
        tool = execute(db, "get_student", {"student_id": student["id"]})
        assert "Original quiz" not in tool and "New quiz" in tool
    history = client.get(f"/api/students/{student['id']}/grade-history").json()
    assert history["active_section_id"] == sections[1]["id"]
    assert len(history["sections"]) == 1
    prior = history["sections"][0]
    assert prior["section_id"] == sections[0]["id"] and prior["course"] == "Before course"
    assert {p["assessment_id"]: p["points"] for p in prior["scores"]} == {original: original_points, old_missing: None}
    assert "average" not in prior
    saved = client.put(
        f"/api/assessments/{new_quiz}/scores", json={"scores": [{"student_id": student["id"], "points": 90}]}
    )
    assert saved.status_code == 200
    active = client.get(f"/api/students/{student['id']}").json()
    assert active["average"] == 90 and active["missing"] == 1
    roster = client.get("/api/students", params={"section_id": sections[1]["id"]}).json()
    assert roster[0]["average"] == 90 and roster[0]["missing"] == 1
    back = client.patch(f"/api/students/{student['id']}", json={"section_id": sections[0]["id"]}).json()
    assert back["average"] == original_points and back["missing"] == 1
    assert {p["assessment_id"]: p["points"] for p in back["scores"]} == {original: original_points, old_missing: None}
    after_history = client.get(f"/api/students/{student['id']}/grade-history").json()["sections"]
    assert after_history[0]["section_id"] == sections[1]["id"]
    assert {p["assessment_id"]: p["points"] for p in after_history[0]["scores"]} == {new_quiz: 90, new_missing: None}
    with session_factory() as db:
        rows = {
            sc.assessment_id: (sc.id, sc.points)
            for sc in db.scalars(select(Score).where(Score.student_id == student["id"]))
        }
        assert len(rows) == 4
        assert {aid: rows[aid] for aid in original_rows} == original_rows


def test_ungraded_student_can_move_and_keeps_empty_history(client):
    sections, student, original = classroom(client)
    response = client.patch(f"/api/students/{student['id']}", json={"section_id": sections[1]["id"]})
    assert response.status_code == 200
    assert response.json()["section_id"] == sections[1]["id"]
    assert response.json()["scores"] == []
    history = client.get(f"/api/students/{student['id']}/grade-history").json()
    assert history["sections"][0]["scores"][0]["assessment_id"] == original
    assert history["sections"][0]["scores"][0]["points"] is None


def test_unknown_destination_is_atomic_and_unknown_history_is_404(client):
    sections, student, original = classroom(client)
    response = client.patch(f"/api/students/{student['id']}", json={"section_id": "missing", "name": "Changed"})
    assert response.status_code == 404
    unchanged = client.get(f"/api/students/{student['id']}").json()
    assert unchanged["section_id"] == sections[0]["id"] and unchanged["name"] == "Student"
    assert unchanged["scores"][0]["assessment_id"] == original
    assert client.get("/api/students/missing/grade-history").status_code == 404
    assert client.get(f"/api/students/{student['id']}/grade-history").json()["sections"] == []


def test_return_adds_new_assignments_without_duplicating_previous_rows(client, session_factory):
    sections, student, original = classroom(client)
    client.put(f"/api/assessments/{original}/scores", json={"scores": [{"student_id": student["id"], "points": 75}]})
    with session_factory() as db:
        original_row = db.scalar(select(Score).where(Score.student_id == student["id"]))
        original_row_id = original_row.id
    assert client.patch(f"/api/students/{student['id']}", json={"section_id": sections[1]["id"]}).status_code == 200
    added_while_away = mk_assessment(client, sections[0], title="Added while away")
    returned = client.patch(f"/api/students/{student['id']}", json={"section_id": sections[0]["id"]})
    assert returned.status_code == 200
    assert {s["assessment_id"]: s["points"] for s in returned.json()["scores"]} == {
        original: 75,
        added_while_away: None,
    }
    assert client.patch(f"/api/students/{student['id']}", json={"section_id": sections[0]["id"]}).status_code == 200
    with session_factory() as db:
        rows = list(db.scalars(select(Score).where(Score.student_id == student["id"])))
        assert len(rows) == 2
        assert next(s for s in rows if s.assessment_id == original).id == original_row_id
