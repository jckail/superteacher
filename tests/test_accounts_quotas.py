"""Per-user daily quotas, the global AI budget, onboarding seed, owner mapping."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from superteacher import accounts, ai
from superteacher import reports as svc
from superteacher.config import get_settings
from superteacher.models import OWNER_ID, Course, Student, User
from tests.acct_util import H, build, second_client, sign_in
from tests.ai_fakes import FakeAI, end_turn

INSIGHT = '{"headline":"h","strengths":["s"],"concerns":["c"],"suggestions":["x"]}'


@pytest.fixture(autouse=True)
def configured_fake_provider(monkeypatch):
    # Fake clients model an available provider, including its configured-key admission contract.
    # All transport calls in these tests are replaced; this key never reaches a network.
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "offline-quota-test-key")


def student_ids(c, n):
    return [s["id"] for s in c.get("/api/students").json()][:n]


@pytest.fixture
def user(tmp_path):
    with build(tmp_path, quota_insight_per_day=2, quota_parent_update_per_day=1, quota_chat_per_day=2) as c:
        sign_in(c, tmp_path, "a@example.com")
        yield c


def test_insight_quota_returns_friendly_429_with_reset_time(user, monkeypatch):
    fake = FakeAI(creates=[INSIGHT] * 5)
    monkeypatch.setattr(ai, "client", lambda: fake)
    s1, s2, s3 = student_ids(user, 3)
    assert user.get(f"/api/students/{s1}/insight").status_code == 200
    assert user.get(f"/api/students/{s2}/insight").status_code == 200
    r = user.get(f"/api/students/{s3}/insight")
    assert r.status_code == 429
    d = r.json()["detail"]
    assert d["code"] == "quota_exceeded" and d["kind"] == "insight" and "UTC" in d["message"] and d["resets_at"]
    assert int(r.headers["retry-after"]) > 0
    assert len(fake.create_calls) == 2  # the blocked request never reached the model


def test_cached_and_rule_based_insights_are_free(user, monkeypatch):
    fake = FakeAI(creates=[INSIGHT] * 5)
    monkeypatch.setattr(ai, "client", lambda: fake)
    s1 = student_ids(user, 1)[0]
    for _ in range(5):  # same data -> cache hit after the first generation
        assert user.get(f"/api/students/{s1}/insight").status_code == 200
    assert user.get("/api/auth/me").json()["usage"]["insight"]["used"] == 1


def test_no_ai_configured_costs_no_quota(user, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    monkeypatch.setattr(ai, "client", lambda: None)
    for s in student_ids(user, 4):
        assert user.get(f"/api/students/{s}/insight").json()["source"] == "rules"
    assert user.get("/api/auth/me").json()["usage"]["insight"]["used"] == 0


def test_parent_draft_quota(user, monkeypatch):
    fake = FakeAI(creates=['{"subject":"s","body":"b"}'] * 3)
    monkeypatch.setattr(svc, "make_client", lambda: fake)
    s1, s2 = student_ids(user, 2)
    assert user.post(f"/api/reports/students/{s1}/parent-update", json={"tone": "warm"}, headers=H).status_code == 200
    r = user.post(f"/api/reports/students/{s2}/parent-update", json={"tone": "warm"}, headers=H)
    assert r.status_code == 429 and r.json()["detail"]["kind"] == "parent_update"
    assert len(fake.create_calls) == 1


def test_template_parent_draft_when_no_ai_is_free(user, monkeypatch):
    monkeypatch.setattr(svc, "make_client", lambda: None)
    s1 = student_ids(user, 1)[0]
    for _ in range(3):
        r = user.post(f"/api/reports/students/{s1}/parent-update", json={"tone": "warm"}, headers=H)
        assert r.status_code == 200 and r.json()["source"] == "template"


def test_chat_quota_is_enforced_per_message(user, monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI([end_turn("a"), end_turn("b"), end_turn("c")]))
    with user.websocket_connect("/api/chat/ws") as ws:
        for _ in range(2):
            ws.send_json({"content": "hi"})
            while (ev := ws.receive_json())["type"] not in ("done", "error"):
                pass
            assert ev["type"] == "done"
        ws.send_json({"content": "hi again"})
        ev = ws.receive_json()
        assert ev["type"] == "error" and ev["code"] == "quota_exceeded" and "UTC" in ev["message"] and ev["resets_at"]
        ws.send_json({"type": "reset"})  # the socket stays usable; only metered messages are refused
    assert user.get("/api/auth/me").json()["usage"]["chat"] == {
        "used": 2, "limit": 2, "resets_at": accounts.next_reset().isoformat()
    }  # fmt: skip


def test_quotas_are_per_user(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI(creates=[INSIGHT] * 9))
    with build(tmp_path, quota_insight_per_day=1) as a:
        sign_in(a, tmp_path, "a@example.com")
        b = second_client(a)
        sign_in(b, tmp_path, "b@example.com")
        a1, a2 = student_ids(a, 2)
        assert a.get(f"/api/students/{a1}/insight").status_code == 200
        assert a.get(f"/api/students/{a2}/insight").status_code == 429
        assert b.get(f"/api/students/{student_ids(b, 1)[0]}/insight").status_code == 200


def test_quota_resets_on_the_next_utc_day(user, monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI(creates=[INSIGHT] * 9))
    ids = student_ids(user, 4)
    user.get(f"/api/students/{ids[0]}/insight")
    user.get(f"/api/students/{ids[1]}/insight")
    assert user.get(f"/api/students/{ids[2]}/insight").status_code == 429
    real = accounts.now
    monkeypatch.setattr(accounts, "now", lambda: real() + timedelta(days=1, minutes=1))
    assert user.get(f"/api/students/{ids[2]}/insight").status_code == 200


def test_global_daily_budget_caps_everyone(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI(creates=[INSIGHT] * 9))
    with build(tmp_path, ai_global_daily_budget=2) as a:
        sign_in(a, tmp_path, "a@example.com")
        b = second_client(a)
        sign_in(b, tmp_path, "b@example.com")
        a1, a2 = student_ids(a, 2)
        assert a.get(f"/api/students/{a1}/insight").status_code == 200
        assert a.get(f"/api/students/{a2}/insight").status_code == 200
        r = b.get(f"/api/students/{student_ids(b, 1)[0]}/insight")
        assert r.status_code == 429 and "daily AI budget" in r.json()["detail"]["message"]


def test_budget_off_by_default(tmp_path):
    with build(tmp_path) as c:
        assert c.app.state.auth.settings.ai_global_daily_budget is None


# ── onboarding ──────────────────────────────────────────────────────────
def test_first_login_seeds_a_small_synthetic_classroom_once(tmp_path):
    with build(tmp_path) as c:
        body = sign_in(c, tmp_path, "new@example.com")
        assert body["new_user"] is True
        courses = c.get("/api/courses").json()
        assert [x["name"] for x in courses] == ["Algebra I", "Biology"]
        students = c.get("/api/students").json()
        assert len(students) == 12
        c.post("/api/auth/logout", headers=H)
        again = sign_in(c, tmp_path, "new@example.com")
        assert again["new_user"] is False
        assert len(c.get("/api/students").json()) == 12  # not re-seeded


def test_starter_data_is_deterministic_and_private_to_each_user(tmp_path):
    with build(tmp_path) as a:
        sign_in(a, tmp_path, "a@example.com")
        b = second_client(a)
        sign_in(b, tmp_path, "b@example.com")
        names = lambda c: [s["name"] for s in c.get("/api/students").json()]  # noqa: E731
        assert names(a) == names(b)  # same recipe...
        assert {s["id"] for s in a.get("/api/students").json()}.isdisjoint(
            {s["id"] for s in b.get("/api/students").json()}
        )
        with a.app.state.session_factory() as db:
            owners = db.execute(select(Course.owner_id, func.count()).group_by(Course.owner_id)).all()
            assert len(owners) == 2 and all(n == 2 for _, n in owners)
        assert a.post("/api/courses", json={"name": "Algebra I"}, headers=H).status_code == 409  # own starter name


def test_starter_data_has_valid_metrics_and_no_real_people(tmp_path):
    from superteacher.seed import FIRST, LAST

    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        for s in c.get("/api/students").json():
            first, _, last = s["name"].partition(" ")
            assert first in FIRST and last in LAST
        assert c.get("/api/overview").json()["students"] == 12


def test_seed_demo_is_skipped_at_startup_in_accounts_mode(tmp_path):
    with build(tmp_path, seed_demo_data=True) as c, c.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Student)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 0


# ── passcode mode maps to one implicit owner ────────────────────────────
def test_passcode_mode_uses_the_implicit_owner(tmp_path):
    from tests.sec_util import build as build_passcode
    from tests.sec_util import login

    with build_passcode() as c:
        assert login(c).status_code == 200
        cid = c.post("/api/courses", json={"name": "Algebra"}, headers=H).json()["id"]
        with c.app.state.session_factory() as db:
            assert db.get(Course, cid).owner_id == OWNER_ID
            assert db.get(User, OWNER_ID) is not None
        assert c.request("DELETE", "/api/account", json={"email": "x@y.co"}, headers=H).status_code == 404


def test_owner_adopts_pre_accounts_data_by_configured_email(tmp_path):
    with build(tmp_path, accounts_owner_email="Boss@Example.com") as c:
        with c.app.state.session_factory() as db:
            accounts.ensure_owner(db)
            db.add(Course(name="Legacy", owner_id=OWNER_ID))
            db.commit()
        sign_in(c, tmp_path, "boss@example.com")
        assert [x["name"] for x in c.get("/api/courses").json()] == ["Legacy"]  # their old data, no starter classroom
        other = second_client(c)
        sign_in(other, tmp_path, "someone@example.com")
        assert "Legacy" not in other.get("/api/courses").text
