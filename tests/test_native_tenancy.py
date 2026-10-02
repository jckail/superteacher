"""Native editing, transfer/history and bounded query contracts remain tenant scoped."""

from datetime import timedelta

import pytest

from superteacher import queries
from superteacher.calendar import school_today
from superteacher.models import Student, User
from tests.acct_util import H, build, second_client, sign_in


@pytest.fixture
def native_tenants(tmp_path):
    with build(tmp_path) as alice:
        sign_in(alice, tmp_path, "alice@example.com")
        bob = second_client(alice)
        sign_in(bob, tmp_path, "bob@example.com")
        course = alice.post("/api/courses", json={"name": "Native", "initial_section_name": "P1"}, headers=H)
        assert course.status_code == 201
        course = course.json()
        section = course["sections"][0]
        student = alice.post(
            "/api/students", json={"name": "Native student", "grade_level": 9, "section_id": section["id"]}, headers=H
        ).json()
        assessment = alice.post(
            f"/api/sections/{section['id']}/assessments",
            json={
                "title": "Native test",
                "max_points": 10,
                "due_date": (school_today() - timedelta(days=1)).isoformat(),
            },
            headers=H,
        ).json()["assessments"][0]
        note = alice.post(
            f"/api/students/{student['id']}/notes", json={"body": "Private native note"}, headers=H
        ).json()
        yield alice, bob, course, section, student, assessment, note


def test_native_new_routes_reject_foreign_ids_without_mutation(native_tenants):
    alice, bob, _, section, student, assessment, note = native_tenants
    sid, aid, nid = student["id"], assessment["id"], note["id"]
    before = alice.get(f"/api/students/{sid}").json()
    assert bob.get(f"/api/students/{sid}/grade-history").status_code == 404
    assert bob.patch(f"/api/assessments/{aid}", json={"title": "Stolen"}, headers=H).status_code == 404
    assert bob.patch(f"/api/students/{sid}/notes/{nid}", json={"body": "Stolen"}, headers=H).status_code == 404
    assert bob.delete(f"/api/students/{sid}/notes/{nid}", headers=H).status_code == 404
    assert alice.get(f"/api/students/{sid}").json() == before
    assert alice.get(f"/api/sections/{section['id']}/gradebook").json()["assessments"][0]["title"] == "Native test"
    assert bob.get(f"/api/students?section_id={section['id']}").json() == []
    assert bob.get(f"/api/overview?section_id={section['id']}").json()["students"] == 0


def test_native_transfer_keeps_history_and_blocks_foreign_destination(native_tenants):
    alice, bob, course, _, student, assessment, note = native_tenants
    sid, aid = student["id"], assessment["id"]
    saved = alice.put(
        f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": sid, "points": 20.123456789}]}, headers=H
    )
    assert saved.status_code == 200  # native finite extra credit has no 1.5x cap
    foreign = bob.get("/api/courses").json()[0]["sections"][0]
    assert alice.patch(f"/api/students/{sid}", json={"section_id": foreign["id"]}, headers=H).status_code == 404
    destination = alice.post("/api/sections", json={"course_id": course["id"], "name": "P2"}, headers=H).json()
    moved = alice.patch(f"/api/students/{sid}", json={"section_id": destination["id"]}, headers=H)
    assert moved.status_code == 200
    assert moved.json()["scores"] == [] and moved.json()["average"] is None
    history = alice.get(f"/api/students/{sid}/grade-history").json()
    assert history["sections"][0]["scores"][0]["points"] == 20.123456789
    assert bob.get(f"/api/students/{sid}/grade-history").status_code == 404
    assert (
        alice.patch(f"/api/students/{sid}/notes/{note['id']}", json={"body": "Edited privately"}, headers=H).status_code
        == 200
    )
    assert alice.patch(f"/api/assessments/{aid}", json={"max_points": 20}, headers=H).status_code == 200


def test_bounded_native_query_helpers_scope_candidates_and_input_batches(native_tenants):
    alice, _, _, _, student, _, _ = native_tenants
    with alice.app.state.session_factory() as db:
        from sqlalchemy import select

        owner = db.scalar(select(User.id).where(User.email == "alice@example.com"))
        foreign = db.scalar(select(User.id).where(User.email == "bob@example.com"))
        all_students = list(db.scalars(select(Student)))
        expected = {s.id for s in all_students if s.section.course.owner_id == owner}
        candidates = queries.student_candidates(db, owner, limit=100)
        assert {s.id for s in candidates} == expected
        rows = list(queries.iter_summaries(db, owner, batch_size=2))
        assert {s.id for s, _ in rows} == expected
        assert {s.id for s, _ in queries.summaries_for(db, all_students, owner_id=owner)} == expected
        assert queries.student_candidates(db, foreign, student_id=student["id"]) == []
        assert queries.load_grade_history(db, student["id"], student["section_id"], owner_id=foreign) == []
