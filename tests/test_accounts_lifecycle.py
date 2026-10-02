"""Account export and hard delete: completeness (no orphan rows in any table) and safeguards."""

from sqlalchemy import func, select, text

from superteacher import accounts, ai
from superteacher.db import Base
from superteacher.models import Student
from tests.acct_util import H, build, second_client, sign_in
from tests.ai_fakes import FakeAI


def counts(c) -> dict[str, int]:
    with c.app.state.session_factory() as db:
        return {t: db.scalar(select(func.count()).select_from(Base.metadata.tables[t])) for t in Base.metadata.tables}


def populate(c, monkeypatch):
    sid = c.get("/api/students").json()[0]["id"]
    c.post(f"/api/students/{sid}/notes", json={"body": "a note"}, headers=H)
    monkeypatch.setattr(
        ai, "client", lambda: FakeAI(creates=['{"headline":"h","strengths":[],"concerns":[],"suggestions":[]}'])
    )
    assert c.get(f"/api/students/{sid}/insight").status_code == 200  # creates insights + usage_counters rows
    # Exercise deletion of durable counters independently of AI cache/metering.
    with c.app.state.session_factory() as db:
        owner_id = db.get(Student, sid).section.course.owner_id
        accounts.consume_quota(db, c.app.state.auth.settings, owner_id, "chat")
    return sid


def test_delete_removes_every_row_of_the_user(tmp_path, monkeypatch):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "gone@example.com")
        populate(c, monkeypatch)
        before = counts(c)
        for t in ("users", "sessions", "courses", "sections", "students", "assessments", "scores", "attendance",
                  "notes", "insights", "usage_counters", "login_tokens"):  # fmt: skip
            assert before[t] > 0, t
        r = c.request("DELETE", "/api/account", json={"email": " GONE@example.com "}, headers=H)
        assert r.status_code == 204
        after = counts(c)
        assert {t: n for t, n in after.items() if n and t != "ai_budget"} == {}, after  # ai_budget: anonymous aggregate
        assert c.get("/api/overview").status_code == 401  # session gone with the account
        assert "st_session" not in c.cookies or c.cookies.get("st_session") in (None, "")
        with c.app.state.session_factory() as db:  # also without FK enforcement: no orphans anywhere
            for q in (
                "select count(*) from students where section_id not in (select id from sections)",
                "select count(*) from scores where student_id not in (select id from students)",
                "select count(*) from scores where assessment_id not in (select id from assessments)",
                "select count(*) from attendance where student_id not in (select id from students)",
                "select count(*) from notes where student_id not in (select id from students)",
                "select count(*) from insights where student_id not in (select id from students)",
            ):
                assert db.execute(text(q)).scalar() == 0, q


def test_delete_leaves_other_users_untouched(tmp_path, monkeypatch):
    with build(tmp_path) as a:
        sign_in(a, tmp_path, "a@example.com")
        b = second_client(a)
        sign_in(b, tmp_path, "b@example.com")
        populate(b, monkeypatch)
        b_before = dict(counts(a))
        n_a = dict(counts(a))
        a.request("DELETE", "/api/account", json={"email": "a@example.com"}, headers=H)
        after = counts(a)
        assert b.get("/api/overview").status_code == 200 and len(b.get("/api/students").json()) == 12
        assert after["users"] == n_a["users"] - 1 and after["students"] == b_before["students"] - 12


def test_delete_needs_typed_email_and_csrf_header(tmp_path):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        assert c.request("DELETE", "/api/account", json={"email": "a@example.com"}).status_code == 403  # no CSRF header
        assert c.request("DELETE", "/api/account", json={"email": "b@example.com"}, headers=H).status_code == 422
        assert c.request("DELETE", "/api/account", json={"email": ""}, headers=H).status_code == 422
        assert c.request("DELETE", "/api/account", json={}, headers=H).status_code == 422
        assert c.request(
            "DELETE", "/api/account", json={"email": "a@example.com"}, headers={**H, "Origin": "https://evil.example"}
        ).status_code == 403  # fmt: skip
        assert c.get("/api/overview").status_code == 200  # nothing was deleted by any refused attempt
        assert c.request("DELETE", "/api/account", json={"email": "a@example.com"}, headers=H).status_code == 204


def test_delete_requires_a_session(tmp_path):
    with build(tmp_path) as c:
        assert c.request("DELETE", "/api/account", json={"email": "a@example.com"}, headers=H).status_code == 401


def test_a_deleted_user_can_sign_up_again_with_a_fresh_account(tmp_path):
    with build(tmp_path) as c:
        first = sign_in(c, tmp_path, "again@example.com")
        c.request("DELETE", "/api/account", json={"email": "again@example.com"}, headers=H)
        again = sign_in(c, tmp_path, "again@example.com")
        assert first["new_user"] and again["new_user"]
        assert len(c.get("/api/students").json()) == 12


def test_export_contains_the_users_data_and_nothing_else(tmp_path, monkeypatch):
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        sid = populate(c, monkeypatch)
        r = c.get("/api/account/export")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
        assert "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
        doc = r.json()
        assert doc["account"]["email"] == "a@example.com"
        students = [s for co in doc["courses"] for sec in co["sections"] for s in sec["students"]]
        assert len(students) == 12 and [co["name"] for co in doc["courses"]] == ["Algebra I", "Biology"]
        mine = next(s for s in students if s["id"] == sid)
        assert (
            mine["notes"][0]["body"] == "a note"
            and mine["insight"]["payload"]
            and mine["scores"]
            and mine["attendance"]
        )
        assert "token" not in r.text and "session" not in r.text.lower()


def test_export_requires_a_session(tmp_path):
    with build(tmp_path) as c:
        assert c.get("/api/account/export").status_code == 401


def test_export_retains_grade_history_after_a_section_transfer(tmp_path):
    from superteacher.models import Course, Score, Section, Student

    with build(tmp_path) as c:
        sign_in(c, tmp_path, "history@example.com")
        sid = c.get("/api/students").json()[0]["id"]
        with c.app.state.session_factory() as db:
            student = db.get(Student, sid)
            previous = db.get(Section, student.section_id)
            original_course = db.get(Course, previous.course_id)
            original_section_id, original_course_id = previous.id, original_course.id
            moved = db.scalar(select(Section).where(Section.id != previous.id))
            student.section_id = moved.id
            expected_scores = db.scalar(select(func.count()).select_from(Score).where(Score.student_id == sid))
            db.commit()
        doc = c.get("/api/account/export").json()
        exported = next(
            s for co in doc["courses"] for section in co["sections"] for s in section["students"] if s["id"] == sid
        )
        assert len(exported["scores"]) == expected_scores
        assert all(score["section_id"] == original_section_id for score in exported["scores"])
        assert all(score["course_id"] == original_course_id for score in exported["scores"])
        assert all(score["title"] and score["max_points"] > 0 and score["due_date"] for score in exported["scores"])


def test_export_does_not_disclose_foreign_assessment_metadata(tmp_path):
    from superteacher.models import Assessment, Course, Score, Section, Student, User

    with build(tmp_path) as c:
        sign_in(c, tmp_path, "mine@example.com")
        sid = c.get("/api/students").json()[0]["id"]
        with c.app.state.session_factory() as db:
            other = User(email="foreign@example.com")
            db.add(other)
            db.flush()
            course = Course(name="Private foreign course", owner_id=other.id)
            db.add(course)
            db.flush()
            section = Section(name="Private foreign section", course_id=course.id)
            db.add(section)
            db.flush()
            assessment = Assessment(title="Private foreign assessment", section_id=section.id)
            db.add(assessment)
            db.flush()
            # A malformed legacy relationship must not reveal a different tenant.
            db.add(Score(student_id=db.get(Student, sid).id, assessment_id=assessment.id, points=50))
            foreign_id = assessment.id
            db.commit()
        response = c.get("/api/account/export")
        assert response.status_code == 200
        assert "Private foreign" not in response.text and foreign_id not in response.text
