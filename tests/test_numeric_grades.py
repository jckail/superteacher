"""Maximum edits remain atomic and raw grade exports retain float precision."""

import csv
import io
import math
from datetime import timedelta

import pytest
from sqlalchemy import select

from superteacher import metrics
from superteacher.calendar import school_today
from superteacher.models import Assessment, Score
from superteacher.queries import load_students
from tests.test_api import mk_class, mk_student
from tests.test_backend_audit import mk_assessment


def _finite(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _reads(client, section, student):
    paths = [
        f"/api/sections/{section['id']}/gradebook",
        f"/api/students/{student['id']}",
        f"/api/students/{student['id']}/grade-history",
        "/api/students",
        "/api/overview",
        f"/api/reports/sections/{section['id']}/summary",
    ]
    result = {}
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, response.text
        result[path] = response.json()
        _finite(result[path])
    response = client.get(f"/api/reports/sections/{section['id']}/gradebook.csv")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
    for row in rows[1:]:
        for cell in [row[1], *row[3:]]:
            if cell:
                assert math.isfinite(float(cell))
    result["csv"] = rows
    return result


def _stored(session_factory, assessment_id, student_id):
    with session_factory() as db:
        assessment = db.get(Assessment, assessment_id)
        fields = {column.name: getattr(assessment, column.name) for column in Assessment.__table__.columns}
        scores = {
            score.id: (score.student_id, score.assessment_id, score.points)
            for score in db.scalars(select(Score).where(Score.assessment_id == assessment_id))
        }
        student = load_students(db, student_id=student_id)[0]
        fingerprint = metrics.fingerprint(student, metrics.compute(student))
        return fields, scores, fingerprint


@pytest.mark.parametrize("maximum", [1e-308, 1e-305])
@pytest.mark.parametrize("transferred", [False, True])
@pytest.mark.parametrize("future", [False, True])
def test_overflowing_maximum_edit_preserves_all_fields_scores_and_reads(
    client, session_factory, maximum, transferred, future
):
    course, section = mk_class(client)
    student = mk_student(client, section)
    due = (school_today() + timedelta(days=10 if future else -3)).isoformat()
    assessment_id = mk_assessment(client, section, title="Original", kind="test", due=due, mx=100)
    saved = client.put(
        f"/api/assessments/{assessment_id}/scores",
        json={"scores": [{"student_id": student["id"], "points": 100}]},
    )
    assert saved.status_code == 200
    if transferred:
        destination = client.post("/api/sections", json={"course_id": course["id"], "name": "P2"}).json()
        assert client.patch(f"/api/students/{student['id']}", json={"section_id": destination["id"]}).status_code == 200
    before_reads = _reads(client, section, student)
    before_stored = _stored(session_factory, assessment_id, student["id"])
    response = client.patch(
        f"/api/assessments/{assessment_id}",
        json={
            "max_points": maximum,
            "title": "Should not persist",
            "kind": "quiz",
            "due_date": (school_today() + timedelta(days=20)).isoformat(),
        },
    )
    assert response.status_code == 422
    assert _stored(session_factory, assessment_id, student["id"]) == before_stored
    assert _reads(client, section, student) == before_reads


def test_finite_extra_credit_maximum_edit_preserves_points(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    assessment_id = mk_assessment(client, section, mx=100)
    assert (
        client.put(
            f"/api/assessments/{assessment_id}/scores",
            json={"scores": [{"student_id": student["id"], "points": 100}]},
        ).status_code
        == 200
    )
    response = client.patch(f"/api/assessments/{assessment_id}", json={"max_points": 0.5})
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["points"][assessment_id] == 100
    assert row["average"] == 20000
    reads = _reads(client, section, student)
    assert reads[f"/api/students/{student['id']}"]["scores"][0]["pct"] == 20000
    assert reads["csv"][1][3] == "100"


def test_tiny_maximum_allows_zero_and_ungraded_scores(client):
    _, section = mk_class(client)
    student = mk_student(client, section, "Zero")
    ungraded = mk_student(client, section, "Ungraded")
    assessment_id = mk_assessment(client, section, mx=100)
    assert (
        client.put(
            f"/api/assessments/{assessment_id}/scores",
            json={"scores": [{"student_id": student["id"], "points": 0}]},
        ).status_code
        == 200
    )
    response = client.patch(f"/api/assessments/{assessment_id}", json={"max_points": 1e-308})
    assert response.status_code == 200
    points = {row["student_id"]: row["points"][assessment_id] for row in response.json()["rows"]}
    assert points == {student["id"]: 0, ungraded["id"]: None}
    _reads(client, section, student)


@pytest.mark.parametrize("maximum,points", [(0.01, 0.004), (1.23456789, 1.123456789)])
def test_csv_points_and_maximum_round_trip_without_precision_loss(client, maximum, points):
    _, section = mk_class(client)
    student = mk_student(client, section)
    assessment_id = mk_assessment(client, section, title="Precise", mx=maximum)
    assert (
        client.put(
            f"/api/assessments/{assessment_id}/scores",
            json={"scores": [{"student_id": student["id"], "points": points}]},
        ).status_code
        == 200
    )
    reads = _reads(client, section, student)
    header, row = reads["csv"]
    assert float(header[3].removeprefix("Precise (").removesuffix(" pts)")) == maximum
    assert float(row[3]) == points
    assert reads[f"/api/students/{student['id']}"]["scores"][0]["points"] == points


def test_multiple_extreme_finite_extra_credit_scores_keep_aggregates_finite(client):
    _, section = mk_class(client)
    student = mk_student(client, section)
    for title in ["First", "Second"]:
        response = client.post(
            f"/api/sections/{section['id']}/assessments",
            json={"title": title, "max_points": 100},
        )
        assert response.status_code == 201
        assessment = next(a for a in response.json()["assessments"] if a["title"] == title)
        response = client.put(
            f"/api/assessments/{assessment['id']}/scores",
            json={"scores": [{"student_id": student["id"], "points": 1e308}]},
        )
        assert response.status_code == 200
        _finite(response.json())
    _reads(client, section, student)
