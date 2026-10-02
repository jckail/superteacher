"""Assessment edits must preserve scores while refreshing derived metrics."""

from datetime import timedelta

import pytest

from superteacher.calendar import school_today
from tests.test_api import mk_class, mk_student
from tests.test_backend_audit import mk_assessment


def test_assessment_maximum_edit_preserves_points_and_refreshes_metrics(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    aid = mk_assessment(client, section)
    client.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": student["id"], "points": 9}]})

    response = client.patch(f"/api/assessments/{aid}", json={"max_points": 20})
    assert response.status_code == 200
    gradebook = response.json()
    assert gradebook["assessments"][0]["max_points"] == 20
    assert gradebook["rows"][0]["points"][aid] == 9
    assert gradebook["rows"][0]["average"] == 45
    detail = client.get(f"/api/students/{student['id']}").json()
    assert detail["scores"][0]["points"] == 9
    assert detail["scores"][0]["pct"] == 45
    assert detail["average"] == 45 and detail["letter"] == "F"
    assert client.get("/api/overview").json()["average"] == 45

    # Lowering a maximum never silently trims existing extra-credit scores.
    lowered = client.patch(f"/api/assessments/{aid}", json={"max_points": 1}).json()
    assert lowered["rows"][0]["points"][aid] == 9
    assert lowered["rows"][0]["average"] == 900


def test_assessment_metadata_edit_updates_student_details_and_due_metrics(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    aid = mk_assessment(client, section)
    tomorrow = (school_today() + timedelta(days=1)).isoformat()
    response = client.patch(
        f"/api/assessments/{aid}", json={"title": "  Final quiz  ", "kind": "quiz", "due_date": tomorrow}
    )
    assert response.status_code == 200
    assessment = response.json()["assessments"][0]
    assert assessment["title"] == "Final quiz"
    assert assessment["kind"] == "quiz" and assessment["due_date"] == tomorrow
    assert assessment["max_points"] == 10
    detail = client.get(f"/api/students/{student['id']}").json()
    assert detail["missing"] == 0 and detail["homework_rate"] is None
    assert detail["scores"][0]["title"] == "Final quiz"
    assert detail["scores"][0]["kind"] == "quiz"


def test_assessment_kind_edit_recalculates_category_weights(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    homework = mk_assessment(client, section)
    test = mk_assessment(client, section, title="Exam", kind="test", mx=100)
    for assessment_id, points in [(homework, 10), (test, 0)]:
        client.put(
            f"/api/assessments/{assessment_id}/scores",
            json={"scores": [{"student_id": student["id"], "points": points}]},
        )
    original = client.get(f"/api/students/{student['id']}").json()
    assert original["average"] == pytest.approx(100 * 0.25 / 0.65)
    updated = client.patch(f"/api/assessments/{homework}", json={"kind": "test"}).json()
    assert updated["rows"][0]["average"] == pytest.approx(10 / 110 * 100)
    assert updated["rows"][0]["points"] == {homework: 10, test: 0}


@pytest.mark.parametrize(
    "body",
    [
        {"title": None},
        {"kind": None},
        {"due_date": None},
        {"max_points": None},
        {"title": "  "},
        {"title": "x" * 121},
        {"kind": "invalid"},
        {"due_date": "invalid"},
        {"max_points": 0},
        {"max_points": -1},
        {"max_points": 1_000_001},
        {"max_points": "NaN"},
        {"max_points": "Infinity"},
    ],
)
def test_invalid_assessment_edits_do_not_mutate(client, body):
    _, section = mk_class(client)
    aid = mk_assessment(client, section)
    url = f"/api/sections/{section['id']}/gradebook"
    original = client.get(url).json()
    assert client.patch(f"/api/assessments/{aid}", json=body).status_code == 422
    assert client.get(url).json() == original


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_assessment_maximum_returns_validation_error(client, value):
    _, section = mk_class(client)
    aid = mk_assessment(client, section)
    response = client.patch(
        f"/api/assessments/{aid}",
        content=f'{{"max_points":{value}}}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_missing_assessment_edit_returns_404(client):
    assert client.patch("/api/assessments/missing", json={"title": "Updated"}).status_code == 404
