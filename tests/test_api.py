from datetime import date, timedelta


def mk_class(client):
    course = client.post("/api/courses", json={"name": "Algebra"}).json()
    sec = client.post("/api/sections", json={"course_id": course["id"], "name": "P1"}).json()
    return course, sec


def mk_student(client, sec, name="Ada Lovelace"):
    return client.post("/api/students", json={"name": name, "grade_level": 9, "section_id": sec["id"]}).json()


def test_health_and_empty_overview(client):
    assert client.get("/api/health").json()["status"] == "healthy"
    o = client.get("/api/overview").json()
    assert o["students"] == 0 and o["average"] is None


def test_duplicate_course_and_section_conflict(client):
    course, _ = mk_class(client)
    assert client.post("/api/courses", json={"name": "Algebra"}).status_code == 409
    assert client.post("/api/sections", json={"course_id": course["id"], "name": "P1"}).status_code == 409
    assert client.post("/api/sections", json={"course_id": "nope", "name": "X"}).status_code == 404


def test_student_crud_and_ids_never_collide(client):
    _, sec = mk_class(client)
    a, b = mk_student(client, sec, "A"), mk_student(client, sec, "B")
    assert client.delete(f"/api/students/{a['id']}").status_code == 204
    c = mk_student(client, sec, "C")  # old scheme (count+1) would have reused B's id
    assert len({b["id"], c["id"]}) == 2
    assert client.patch(f"/api/students/{c['id']}", json={"name": "C2"}).json()["name"] == "C2"
    assert client.get("/api/students/missing").status_code == 404
    assert client.post("/api/students", json={"name": "x", "grade_level": 13, "section_id": sec["id"]}).status_code == 422


def test_gradebook_flow_and_metrics(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    past = (date.today() - timedelta(days=3)).isoformat()
    gb = client.post(f"/api/sections/{sec['id']}/assessments",
                     json={"title": "HW1", "kind": "homework", "max_points": 10, "due_date": past}).json()
    aid = gb["assessments"][0]["id"]
    assert gb["rows"][0]["points"][aid] is None  # explicit "missing"
    detail = client.get(f"/api/students/{s['id']}").json()
    assert detail["missing"] == 1 and detail["average"] is None

    gb = client.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": s["id"], "points": 9}]}).json()
    assert gb["rows"][0]["average"] == 90 and gb["rows"][0]["letter"] == "A-"
    detail = client.get(f"/api/students/{s['id']}").json()
    assert detail["gpa"] == 3.7 and detail["missing"] == 0 and detail["homework_rate"] == 100

    bad = client.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": s["id"], "points": 500}]})
    assert bad.status_code == 422
    other = client.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": "zzz", "points": 1}]})
    assert other.status_code == 422


def test_attendance_roundtrip_and_rate(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    today = date.today()
    for i, status in enumerate(["present", "absent", "tardy", "excused"]):
        day = (today - timedelta(days=i)).isoformat()
        r = client.put(f"/api/sections/{sec['id']}/attendance", json={"day": day, "marks": [{"student_id": s["id"], "status": status}]})
        assert r.status_code == 200
    # re-marking the same day updates, not duplicates
    client.put(f"/api/sections/{sec['id']}/attendance", json={"day": today.isoformat(), "marks": [{"student_id": s["id"], "status": "absent"}]})
    d = client.get(f"/api/students/{s['id']}").json()
    assert len(d["attendance"]) == 4 and d["absences"] == 2
    # excused is excluded: counted = [absent, absent, tardy] -> 1/3 attended
    assert round(d["attendance_rate"]) == 33


def test_notes_and_rule_insight_without_api_key(client):
    _, sec = mk_class(client)
    s = mk_student(client, sec)
    assert client.post(f"/api/students/{s['id']}/notes", json={"body": "Spoke with parent"}).status_code == 201
    assert client.get(f"/api/students/{s['id']}").json()["notes"][0]["body"] == "Spoke with parent"
    ins = client.get(f"/api/students/{s['id']}/insight").json()
    assert ins["source"] == "rules" and ins["headline"]


def test_seeded_data_has_stories_and_filters(seeded):
    o = seeded.get("/api/overview").json()
    assert o["students"] == 45 and o["at_risk"] >= 1 and o["attention"]
    assert sum(o["distribution"].values()) <= 45
    all_ = seeded.get("/api/students").json()
    risky = seeded.get("/api/students", params={"risk": "at_risk"}).json()
    assert 0 < len(risky) < len(all_)
    assert all(r["risk"] == "at_risk" for r in risky)
    q = seeded.get("/api/students", params={"q": all_[0]["name"][:3]}).json()
    assert q and all(all_[0]["name"][:3].lower() in r["name"].lower() for r in q)
    # seeding is idempotent: a second startup must not duplicate or wipe anything
    assert len(seeded.get("/api/courses").json()) == 3


def test_csv_import_skips_bad_rows(client):
    _, sec = mk_class(client)
    csv_text = "name,grade_level\nAda Lovelace,10\n,9\nGrace Hopper,99\nada lovelace,10\nAlan Turing\n"
    r = client.post(f"/api/sections/{sec['id']}/import", json={"csv": csv_text}).json()
    assert r["created"] == 2 and len(r["skipped"]) == 3
    names = sorted(s["name"] for s in client.get("/api/students").json())
    assert names == ["Ada Lovelace", "Alan Turing"]
    assert client.post("/api/sections/zzz/import", json={"csv": "a"}).status_code == 404
