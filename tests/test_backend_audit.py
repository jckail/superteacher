"""Regression tests from the backend audit (validation, cascades, sections, CSV, perf paths)."""

from datetime import timedelta

import pytest

from superteacher.calendar import school_today
from tests.test_api import mk_class, mk_student

PAST = (school_today() - timedelta(days=3)).isoformat()


def mk_assessment(client, sec, title="HW1", kind="homework", due=PAST, mx=10):
    gb = client.post(
        f"/api/sections/{sec['id']}/assessments", json={"title": title, "kind": kind, "max_points": mx, "due_date": due}
    ).json()
    return next(a for a in gb["assessments"] if a["title"] == title)["id"]


def test_names_unique_case_insensitively_and_blank_rejected(client):
    course, _ = mk_class(client)
    assert client.post("/api/courses", json={"name": "  algebra "}).status_code == 409
    assert client.post("/api/sections", json={"course_id": course["id"], "name": "p1"}).status_code == 409
    assert client.post("/api/courses", json={"name": "   "}).status_code == 422
    assert client.post("/api/sections", json={"course_id": course["id"], "name": " "}).status_code == 422
    _, sec = course, client.get("/api/courses").json()[0]["sections"][0]
    assert (
        client.post("/api/students", json={"name": "  ", "grade_level": 9, "section_id": sec["id"]}).status_code == 422
    )
    s = mk_student(client, sec, "  Ada  ")
    assert s["name"] == "Ada"
    assert client.patch(f"/api/students/{s['id']}", json={"name": "   "}).status_code == 422
    assert client.post(f"/api/students/{s['id']}/notes", json={"body": "  "}).status_code == 422


def test_patch_null_fields_rejected_not_500(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    for body in ({"section_id": None}, {"grade_level": None}, {"name": None}):
        assert client.patch(f"/api/students/{s['id']}", json=body).status_code == 422


def test_new_student_gets_missing_scores_for_existing_assessments(client):
    _, sec = mk_class(client)
    aid = mk_assessment(client, sec)
    s = mk_student(client, sec)  # enrolled after the assessment exists
    d = client.get(f"/api/students/{s['id']}").json()
    assert d["missing"] == 1 and len(d["scores"]) == 1
    client.post(f"/api/sections/{sec['id']}/import", json={"csv": "Grace,10"})
    gb = client.get(f"/api/sections/{sec['id']}/gradebook").json()
    assert all(aid in r["points"] and r["points"][aid] is None for r in gb["rows"])
    assert len(gb["rows"]) == 2


def test_moving_ungraded_student_between_sections_swaps_empty_scores(client):
    course, sec1 = mk_class(client)
    sec2 = client.post("/api/sections", json={"course_id": course["id"], "name": "P2"}).json()
    a1 = mk_assessment(client, sec1, "A1")
    a2 = mk_assessment(client, sec2, "B1")
    s = mk_student(client, sec1)
    d = client.patch(f"/api/students/{s['id']}", json={"section_id": sec2["id"]}).json()
    assert [p["assessment_id"] for p in d["scores"]] == [a2]  # old section's assignments must not leak
    assert d["missing"] == 1 and d["average"] is None
    history = client.get(f"/api/students/{s['id']}/grade-history").json()
    assert history["sections"][0]["scores"][0]["assessment_id"] == a1
    assert history["sections"][0]["scores"][0]["points"] is None
    # and the old section's gradebook no longer lists them
    assert client.get(f"/api/sections/{sec1['id']}/gradebook").json()["rows"] == []
    # old section can't be graded for them any more
    r = client.put(f"/api/assessments/{a1}/scores", json={"scores": [{"student_id": s["id"], "points": 1}]})
    assert r.status_code == 422


def test_duplicate_entries_in_one_request_do_not_500(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    aid = mk_assessment(client, sec)
    client.post  # noqa: B018
    r = client.put(
        f"/api/assessments/{aid}/scores",
        json={"scores": [{"student_id": s["id"], "points": 1}, {"student_id": s["id"], "points": 7}]},
    )
    assert r.status_code == 200 and r.json()["rows"][0]["points"][aid] == 7
    marks = [{"student_id": s["id"], "status": "absent"}, {"student_id": s["id"], "status": "present"}]
    r = client.put(f"/api/sections/{sec['id']}/attendance", json={"marks": marks})
    assert r.status_code == 200 and r.json()["rows"][0]["status"] == "present"


def test_invalid_numbers_and_oversized_batches(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    aid = mk_assessment(client, sec)
    for pts in (-1, "NaN", "Infinity"):
        r = client.put(
            f"/api/assessments/{aid}/scores",
            content=f'{{"scores":[{{"student_id":"{s["id"]}","points":{pts}}}]}}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
    for mx in (0, -5, 1e12):
        assert (
            client.post(f"/api/sections/{sec['id']}/assessments", json={"title": "X", "max_points": mx}).status_code
            == 422
        )
    big = [{"student_id": s["id"], "points": 1}] * 1001
    assert client.put(f"/api/assessments/{aid}/scores", json={"scores": big}).status_code == 422
    big = [{"student_id": s["id"], "status": "present"}] * 1001
    assert client.put(f"/api/sections/{sec['id']}/attendance", json={"marks": big}).status_code == 422


def test_attendance_is_scoped_to_section(client):
    course, sec1 = mk_class(client)
    sec2 = client.post("/api/sections", json={"course_id": course["id"], "name": "P2"}).json()
    a, b = mk_student(client, sec1, "A"), mk_student(client, sec2, "B")
    day = school_today().isoformat()
    client.put(
        f"/api/sections/{sec2['id']}/attendance",
        json={"day": day, "marks": [{"student_id": b["id"], "status": "absent"}]},
    )
    r = client.put(
        f"/api/sections/{sec1['id']}/attendance",
        json={"day": day, "marks": [{"student_id": a["id"], "status": "present"}]},
    )
    assert r.status_code == 200
    assert (
        client.put(
            f"/api/sections/{sec1['id']}/attendance",
            json={"day": day, "marks": [{"student_id": b["id"], "status": "present"}]},
        ).status_code
        == 422
    )
    sheet = client.get(f"/api/sections/{sec2['id']}/attendance", params={"day": day}).json()
    assert sheet["rows"][0]["status"] == "absent"


def test_search_treats_wildcards_literally(client):
    _, sec = mk_class(client)
    mk_student(client, sec, "Ada")
    mk_student(client, sec, "Bo_b")
    assert [s["name"] for s in client.get("/api/students", params={"q": "%"}).json()] == []
    assert [s["name"] for s in client.get("/api/students", params={"q": "_"}).json()] == ["Bo_b"]


def test_delete_student_and_assessment_cascade(client, session_factory):
    from sqlalchemy import func, select

    from superteacher.models import AttendanceRecord, Note, Score

    _, sec = mk_class(client)
    s = mk_student(client, sec)
    aid = mk_assessment(client, sec)
    client.post(f"/api/students/{s['id']}/notes", json={"body": "hi"})
    client.put(f"/api/sections/{sec['id']}/attendance", json={"marks": [{"student_id": s["id"], "status": "present"}]})
    assert client.delete(f"/api/assessments/{aid}").status_code == 200
    assert client.delete(f"/api/students/{s['id']}").status_code == 204
    with session_factory() as db:
        for m in (Score, Note, AttendanceRecord):
            assert db.scalar(select(func.count()).select_from(m)) == 0


def test_csv_import_edge_cases(client):
    _, sec = mk_class(client)
    url = f"/api/sections/{sec['id']}/import"
    text = '﻿name,grade_level\n"Hopper, Grace",11\n"  Ada   Lovelace ",9\nADA LOVELACE,9\n\n,\nBob,abc\nCy,9.5\nDee,0\n'
    r = client.post(url, json={"csv": text}).json()
    assert r["created"] == 2 and len(r["skipped"]) == 4
    names = sorted(s["name"] for s in client.get("/api/students").json())
    assert names == ["Ada Lovelace", "Hopper, Grace"]
    assert client.post(url, json={"csv": 'a"b\x00c,9\n"unterminated,9'}).status_code in (200, 422)
    assert client.post(url, json={"csv": "x" * 500_001}).status_code == 422
    assert client.post(url, json={"csv": "a\n" * 5001}).status_code == 422


def test_gradebook_future_assessment_not_counted(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    future = (school_today() + timedelta(days=5)).isoformat()
    aid = mk_assessment(client, sec, "Future", "test", future, 100)
    client.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": s["id"], "points": 10}]})
    d = client.get(f"/api/students/{s['id']}").json()
    assert d["average"] is None and d["missing"] == 0


def test_list_and_detail_agree(seeded):
    """The bulk (column-tuple) path used by list/overview must match the ORM path used by detail."""
    for row in seeded.get("/api/students").json()[:15]:
        d = seeded.get(f"/api/students/{row['id']}").json()
        for k in (
            "average",
            "letter",
            "gpa",
            "trend",
            "attendance_rate",
            "homework_rate",
            "missing",
            "risk",
            "risk_reasons",
        ):
            assert row[k] == d[k], (row["name"], k)
    gb_ids = {
        r["student_id"]
        for sec in seeded.get("/api/courses").json()[0]["sections"]
        for r in seeded.get(f"/api/sections/{sec['id']}/gradebook").json()["rows"]
    }
    assert gb_ids


@pytest.mark.parametrize("path", ["/api/students", "/api/overview"])
def test_listing_query_count_is_constant(seeded, engine, path):
    from sqlalchemy import event

    n = []
    event.listen(engine, "before_cursor_execute", lambda *a: n.append(1))
    seeded.get(path)
    assert len(n) <= 8


def test_app_database_factory_applies_without_test_overrides(engine, session_factory):
    from fastapi.testclient import TestClient

    from superteacher.config import Settings
    from superteacher.main import create_app

    app = create_app(engine=engine, session_factory=session_factory, seed=False, settings=Settings(auth_disabled=True))
    with TestClient(app) as c:
        _, sec = mk_class(c)
        student = mk_student(c, sec)
        assert c.get("/api/students").json()[0]["id"] == student["id"]


def test_unknown_api_path_does_not_return_spa_html(engine, session_factory, tmp_path):
    from fastapi.testclient import TestClient

    from superteacher.config import Settings
    from superteacher.main import create_app

    (tmp_path / "index.html").write_text("<html>app</html>")
    app = create_app(
        engine=engine,
        session_factory=session_factory,
        seed=False,
        settings=Settings(auth_disabled=True, static_dir=str(tmp_path)),
    )
    with TestClient(app) as c:
        assert c.get("/roster").status_code == 200
        response = c.get("/api/missing")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


def test_database_failure_reports_unhealthy_status(client):
    from superteacher.db import get_db

    class BrokenSession:
        def execute(self, _):
            raise RuntimeError("private database connection details")

    client.app.dependency_overrides[get_db] = lambda: BrokenSession()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "error", "ai": False}
