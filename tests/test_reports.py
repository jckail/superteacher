import csv
import io
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from superteacher import reports as svc
from superteacher.config import get_settings
from superteacher.routers.reports import router as reports_router


@pytest.fixture(autouse=True)
def _mounted(request):
    """Mount the router on whichever app fixture the test uses (until main.py registers it)."""
    for name in ("client", "seeded"):
        if name in request.fixturenames:
            app = request.getfixturevalue(name).app
            if not any(getattr(r, "path", "").startswith("/api/reports") for r in app.routes):
                n = len(app.router.routes)
                app.include_router(reports_router, prefix="/api")
                # a built SPA registers a catch-all; our routes must win over it
                app.router.routes[:] = app.router.routes[n:] + app.router.routes[:n]


def mk_class(client, name="Algebra", sec="P1"):
    course = client.post("/api/courses", json={"name": name}).json()
    return client.post("/api/sections", json={"course_id": course["id"], "name": sec}).json()


def mk_student(client, sec, name):
    return client.post("/api/students", json={"name": name, "grade_level": 9, "section_id": sec["id"]}).json()


def mk_assessment(client, sec, title, max_points=100, due=None, kind="test"):
    due = due or (date.today() - timedelta(days=3)).isoformat()
    gb = client.post(f"/api/sections/{sec['id']}/assessments", json={"title": title, "max_points": max_points, "due_date": due, "kind": kind}).json()
    return next(a for a in gb["assessments"] if a["title"] == title)


def set_scores(client, a, scores):
    r = client.put(f"/api/assessments/{a['id']}/scores", json={"scores": [{"student_id": k, "points": v} for k, v in scores.items()]})
    assert r.status_code == 200, r.text


def parse(resp):
    return list(csv.reader(io.StringIO(resp.text.lstrip("﻿"))))


def test_csv_is_attachment_with_points_and_blanks(client):
    sec = mk_class(client)
    a, b = mk_student(client, sec, "Ada"), mk_student(client, sec, "Bob")
    t = mk_assessment(client, sec, "Unit 1", max_points=50)
    set_scores(client, t, {a["id"]: 45, b["id"]: None})
    r = client.get(f"/api/reports/sections/{sec['id']}/gradebook.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith("attachment; filename=")
    rows = parse(r)
    assert rows[0] == ["Student", "Average (%)", "Letter", "Unit 1 (50 pts)"]
    assert rows[1] == ["Ada", "90.0", "A-", "45"]
    assert rows[2] == ["Bob", "", "", ""]


def test_csv_injection_and_escaping(client):
    sec = mk_class(client)
    for n in ['=HYPERLINK("x")', "+1", "-2", "@SUM(A1)", 'Smith, "Jo"']:
        mk_student(client, sec, n)
    mk_assessment(client, sec, "=cmd|' /C calc'!A0")
    rows = parse(client.get(f"/api/reports/sections/{sec['id']}/gradebook.csv"))
    names = {r[0] for r in rows[1:]}
    assert {"'=HYPERLINK(\"x\")", "'+1", "'-2", "'@SUM(A1)", 'Smith, "Jo"'} == names
    assert rows[0][3].startswith("'=cmd")


def test_csv_safe_leaves_numbers_alone():
    assert svc.csv_safe(-5) == -5 and svc.csv_safe(None) == "" and svc.csv_safe("ok") == "ok"
    assert svc.csv_safe("\t=x") == "'\t=x"


def test_summary_stats_match_hand_computation(client):
    sec = mk_class(client)
    ids = [mk_student(client, sec, n)["id"] for n in ("A", "B", "C", "D")]
    t = mk_assessment(client, sec, "Test", max_points=100)
    set_scores(client, t, {ids[0]: 90, ids[1]: 70, ids[2]: 50})  # D missing
    future = mk_assessment(client, sec, "Later", due=(date.today() + timedelta(days=9)).isoformat())
    s = client.get(f"/api/reports/sections/{sec['id']}/summary").json()
    st = next(x for x in s["assessments"] if x["title"] == "Test")
    assert (st["average"], st["median"], st["min"], st["max"], st["graded"]) == (70.0, 70.0, 50.0, 90.0, 3)
    assert st["missing_pct"] == 25.0
    assert next(x for x in s["assessments"] if x["id"] == future["id"])["missing_pct"] is None
    assert s["students"] == 4
    assert s["distribution"] == {"A": 0, "B": 0, "C": 1, "D": 1, "F": 1} or sum(s["distribution"].values()) == 3
    # 90 -> A-, 70 -> C-, 50 -> F
    assert s["distribution"] == {"A": 1, "B": 0, "C": 1, "D": 0, "F": 1}
    assert [x["name"] for x in s["attention"]][0] == "C"  # failing student first
    assert s["average"] == 70.0


def test_summary_attendance_window_and_rate(client):
    sec = mk_class(client)
    a, b = mk_student(client, sec, "A"), mk_student(client, sec, "B")
    today = date.today()
    old = today - timedelta(days=45)
    for day, marks in [
        (today, {a["id"]: "present", b["id"]: "absent"}),
        (today - timedelta(days=1), {a["id"]: "tardy", b["id"]: "excused"}),
        (old, {a["id"]: "absent", b["id"]: "absent"}),
    ]:
        r = client.put(f"/api/sections/{sec['id']}/attendance", json={"day": day.isoformat(), "marks": [{"student_id": k, "status": v} for k, v in marks.items()]})
        assert r.status_code == 200, r.text
    att = client.get(f"/api/reports/sections/{sec['id']}/summary").json()["attendance"]
    assert [d["day"] for d in att] == [(today - timedelta(days=1)).isoformat(), today.isoformat()]
    assert att[0]["rate"] == 100.0  # tardy counts as attended, excused ignored
    assert att[1]["rate"] == 50.0 and att[1]["absent"] == 1


def test_empty_section_summary_and_csv(client):
    sec = mk_class(client)
    s = client.get(f"/api/reports/sections/{sec['id']}/summary").json()
    assert s["students"] == 0 and s["average"] is None and s["assessments"] == [] and s["attendance"] == []
    assert parse(client.get(f"/api/reports/sections/{sec['id']}/gradebook.csv")) == [["Student", "Average (%)", "Letter"]]


def test_404s(client):
    assert client.get("/api/reports/sections/nope/summary").status_code == 404
    assert client.get("/api/reports/sections/nope/gradebook.csv").status_code == 404
    assert client.post("/api/reports/students/nope/parent-update", json={"tone": "warm"}).status_code == 404


def test_bad_tone_rejected(seeded):
    sid = seeded.get("/api/students").json()[0]["id"]
    assert seeded.post(f"/api/reports/students/{sid}/parent-update", json={"tone": "angry"}).status_code == 422


@pytest.mark.parametrize("tone", ["warm", "neutral", "concerned"])
def test_parent_update_template_without_key(seeded, tone):
    stu = seeded.get("/api/students").json()[0]
    r = seeded.post(f"/api/reports/students/{stu['id']}/parent-update", json={"tone": tone})
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "template" and d["subject"] and stu["name"].split()[0] in d["body"]
    others = [s["name"] for s in seeded.get("/api/students").json() if s["id"] != stu["id"]]
    assert not any(n in d["body"] for n in others)


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.prompts, self.text, self.exc = [], text, exc
        self.messages = SimpleNamespace(create=self.create)

    async def create(self, **kw):
        self.prompts.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)])


def _post(seeded, monkeypatch, fake):
    monkeypatch.setattr(svc, "make_client", lambda: fake)
    sid = seeded.get("/api/students").json()[0]["id"]
    return seeded.post(f"/api/reports/students/{sid}/parent-update", json={"tone": "neutral"}), fake


def test_parent_update_ai_path(seeded, monkeypatch):
    fake = FakeClient('Sure! {"subject": "Progress update", "body": "Hello,\\n\\nAlex is doing well in class this term.\\n\\nBest regards,"}')
    r, fake = _post(seeded, monkeypatch, fake)
    assert r.json()["source"] == "ai" and r.json()["subject"] == "Progress update"
    call = fake.prompts[0]
    assert call["model"] == get_settings().anthropic_insight_model and call["max_tokens"] <= 1000
    prompt = call["messages"][0]["content"]
    assert "untrusted" in prompt and "home life" in prompt


@pytest.mark.parametrize("fake", [
    FakeClient("not json at all"),
    FakeClient('{"subject": "", "body": "x"}'),
    FakeClient(exc=RuntimeError("boom")),
])
def test_parent_update_ai_failures_fall_back(seeded, monkeypatch, fake):
    r, _ = _post(seeded, monkeypatch, fake)
    assert r.status_code == 200 and r.json()["source"] == "template"
