"""Course onboarding is one transaction, including its initial section."""

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from superteacher.models import Course, Section


def test_course_with_initial_section_is_atomic_and_trims_names(client):
    response = client.post("/api/courses", json={"name": "  Algebra  ", "initial_section_name": "  Period 1  "})
    assert response.status_code == 201
    course = response.json()
    assert course["name"] == "Algebra"
    assert len(course["sections"]) == 1
    assert course["sections"][0]["name"] == "Period 1"
    assert course["sections"][0]["course_id"] == course["id"]
    assert client.get("/api/courses").json() == [course]


def test_initial_section_failure_leaves_no_orphan_and_retry_succeeds(client, session_factory):
    def reject(mapper, connection, target):
        raise IntegrityError("synthetic rejected section", {}, Exception("synthetic failure"))

    event.listen(Section, "before_insert", reject)
    try:
        response = client.post("/api/courses", json={"name": "Algebra", "initial_section_name": "Period 1"})
        assert response.status_code == 409
    finally:
        event.remove(Section, "before_insert", reject)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Course)) == 0
        assert db.scalar(select(func.count()).select_from(Section)) == 0
    assert client.post("/api/courses", json={"name": "Algebra", "initial_section_name": "Period 1"}).status_code == 201


@pytest.mark.parametrize("section_name", [" ", "x" * 61])
def test_invalid_initial_section_cannot_create_course(client, section_name):
    response = client.post("/api/courses", json={"name": "Algebra", "initial_section_name": section_name})
    assert response.status_code == 422
    assert client.get("/api/courses").json() == []


def test_bare_course_creation_keeps_existing_contract(client):
    response = client.post("/api/courses", json={"name": "Algebra"})
    assert response.status_code == 201
    assert response.json()["sections"] == []
