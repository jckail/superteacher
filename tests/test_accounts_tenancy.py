"""Cross-tenant attack suite: user B must never see or influence user A's data through ANY surface.

Both users have identically named courses/sections/students (overlap is legal and must not confuse anything), and
A's records carry canary strings that must never appear in anything B receives.
"""

import asyncio
import json
import re
from datetime import date

import pytest

from superteacher import ai, ai_tools
from superteacher import reports as svc
from tests.acct_util import H, build, second_client, sign_in
from tests.ai_fakes import FakeAI, end_turn, tool_turn
from tests.sec_util import flatten_routes

A_CANARY = "ALICE-CANARY-STUDENT"
A_NOTE = "ALICE-PRIVATE-NOTE-7731"
TODAY = date.today().isoformat()


def make_class(c, canary: str | None, note: str | None = None) -> dict:
    """Course 'Algebra' / section 'P1' / 'Ada Lovelace' (+ optional canary student), an assessment, scores, notes."""
    cid = c.post("/api/courses", json={"name": "Algebra"}, headers=H).json()["id"]
    sid = c.post("/api/sections", json={"course_id": cid, "name": "P1"}, headers=H).json()["id"]
    names = ["Ada Lovelace"] + ([canary] if canary else [])
    studs = [
        c.post("/api/students", json={"name": n, "grade_level": 9, "section_id": sid}, headers=H).json()["id"]
        for n in names
    ]
    aid = c.post(f"/api/sections/{sid}/assessments", json={"title": "Quiz 1", "max_points": 10}, headers=H).json()[
        "assessments"
    ][0]["id"]
    c.put(f"/api/assessments/{aid}/scores", json={"scores": [{"student_id": s, "points": 7} for s in studs]}, headers=H)
    c.put(
        f"/api/sections/{sid}/attendance",
        json={"day": TODAY, "marks": [{"student_id": s, "status": "absent"} for s in studs]},
        headers=H,
    )
    if note:
        c.post(f"/api/students/{studs[-1]}/notes", json={"body": note}, headers=H)
    return {"course": cid, "section": sid, "students": studs, "assessment": aid}


@pytest.fixture
def world(tmp_path):
    with build(tmp_path) as alice:
        sign_in(alice, tmp_path, "alice@example.com")
        bob = second_client(alice)
        sign_in(bob, tmp_path, "bob@example.com")
        a = make_class(alice, A_CANARY, A_NOTE)
        b = make_class(bob, None)
        yield alice, bob, a, b


def snapshot(c, ids: dict) -> str:
    """Everything A can read about her class, serialised, for before/after comparison."""
    parts = [
        c.get("/api/courses").text,
        c.get("/api/students").text,
        c.get("/api/overview").text,
        c.get(f"/api/sections/{ids['section']}/gradebook").text,
        c.get(f"/api/sections/{ids['section']}/attendance?day={TODAY}").text,
        c.get(f"/api/reports/sections/{ids['section']}/summary").text,
        c.get(f"/api/reports/sections/{ids['section']}/gradebook.csv").text,
    ] + [c.get(f"/api/students/{s}").text for s in ids["students"]]
    return "\n".join(parts)


# ── listings, search, overview, reports: B sees only B ──────────────────
def test_lists_search_and_overview_contain_only_own_rows(world):
    alice, bob, a, b = world
    for path in ("/api/courses", "/api/students", "/api/students?q=Canary", "/api/students?q=ALICE", "/api/overview"):
        text = bob.get(path).text
        assert A_CANARY not in text and A_NOTE not in text, path
    assert bob.get("/api/students?q=ALICE").json() == []
    bob_ids = {s["id"] for s in bob.get("/api/students").json()}
    assert set(b["students"]) <= bob_ids and not bob_ids & set(a["students"])
    course_ids = {x["id"] for x in bob.get("/api/courses").json()}
    assert b["course"] in course_ids and a["course"] not in course_ids
    # each account starts with the same-sized synthetic starter classroom; Alice added 2 students, Bob 1
    starter = len(bob_ids) - 1
    assert bob.get("/api/overview").json()["students"] == starter + 1
    assert alice.get("/api/overview").json()["students"] == starter + 2


def test_filters_by_foreign_ids_return_nothing(world):
    _, bob, a, _ = world
    assert bob.get(f"/api/students?course_id={a['course']}").json() == []
    assert bob.get(f"/api/students?section_id={a['section']}").json() == []
    ov = bob.get(f"/api/overview?course_id={a['course']}&section_id={a['section']}").json()
    assert ov["students"] == 0 and ov["attention"] == []


def test_overlapping_names_are_allowed_per_owner_but_not_within_one(world):
    alice, bob, a, b = world
    assert a["course"] != b["course"]
    assert bob.post("/api/courses", json={"name": "algebra"}, headers=H).status_code == 409  # case-insensitive, own
    assert alice.post("/api/courses", json={"name": "ALGEBRA"}, headers=H).status_code == 409
    assert bob.post("/api/courses", json={"name": "Chemistry"}, headers=H).status_code == 201


# ── every route that takes an id: 404 for foreign ids, nothing changes ──
def _id_routes(ids):
    s, st, a, c = ids["section"], ids["students"][1], ids["assessment"], ids["course"]
    return [
        ("GET", f"/api/students/{st}", None),
        ("PATCH", f"/api/students/{st}", {"name": "Hacked"}),
        ("DELETE", f"/api/students/{st}", None),
        ("POST", f"/api/students/{st}/notes", {"body": "planted"}),
        ("GET", f"/api/students/{st}/insight", None),
        ("POST", f"/api/reports/students/{st}/parent-update", {"tone": "warm"}),
        ("GET", f"/api/sections/{s}/attendance", None),
        ("PUT", f"/api/sections/{s}/attendance", {"day": TODAY, "marks": [{"student_id": st, "status": "present"}]}),
        ("GET", f"/api/sections/{s}/gradebook", None),
        ("POST", f"/api/sections/{s}/assessments", {"title": "Planted"}),
        ("POST", f"/api/sections/{s}/import", {"csv": "Planted Kid,9\n"}),
        ("PUT", f"/api/assessments/{a}/scores", {"scores": [{"student_id": st, "points": 0}]}),
        ("DELETE", f"/api/assessments/{a}", None),
        ("GET", f"/api/reports/sections/{s}/gradebook.csv", None),
        ("GET", f"/api/reports/sections/{s}/summary", None),
        # ids in request bodies
        ("POST", "/api/sections", {"course_id": c, "name": "Planted"}),
        ("POST", "/api/students", {"name": "Planted", "grade_level": 9, "section_id": s}),
    ]


def test_every_id_route_is_404_for_a_foreign_owner(world):
    alice, bob, a, _ = world
    before = snapshot(alice, a)
    for method, path, body in _id_routes(a):
        r = (
            bob.request(method, path, json=body, headers=H)
            if body is not None
            else bob.request(method, path, headers=H)
        )
        assert r.status_code == 404, (method, path, r.status_code, r.text[:200])
        assert A_CANARY not in r.text and A_NOTE not in r.text
        # indistinguishable from an id that never existed
        ghost = re.sub(
            r"/(?:students|sections|assessments)/[0-9a-f]{12}", lambda m: m.group(0)[:-12] + "ffffffffffff", path
        )
        if ghost != path:
            g = (
                bob.request(method, ghost, json=body, headers=H)
                if body is not None
                else bob.request(method, ghost, headers=H)
            )
            assert (g.status_code, g.json()["detail"].split(" ")[0]) == (
                r.status_code,
                r.json()["detail"].split(" ")[0],
            )
    assert snapshot(alice, a) == before, "a cross-tenant request changed Alice's data"


def test_moving_a_student_into_a_foreign_section_is_refused(world):
    alice, bob, a, b = world
    assert (
        bob.patch(f"/api/students/{b['students'][0]}", json={"section_id": a["section"]}, headers=H).status_code == 404
    )
    assert (
        alice.patch(f"/api/students/{a['students'][0]}", json={"section_id": b["section"]}, headers=H).status_code
        == 404
    )
    assert not {s["id"] for s in bob.get("/api/students").json()} & set(a["students"])
    assert b["students"][0] in {s["id"] for s in bob.get("/api/students").json()}


def test_scores_and_attendance_for_foreign_students_in_own_section_are_refused(world):
    alice, bob, a, b = world
    foreign = a["students"][1]
    r = bob.put(
        f"/api/assessments/{b['assessment']}/scores", json={"scores": [{"student_id": foreign, "points": 0}]}, headers=H
    )
    assert r.status_code == 422 and A_CANARY not in r.text
    r = bob.put(
        f"/api/sections/{b['section']}/attendance",
        json={"day": TODAY, "marks": [{"student_id": foreign, "status": "present"}]},
        headers=H,
    )
    assert r.status_code == 422
    assert alice.get(f"/api/students/{foreign}").json()["attendance"][0]["status"] == "absent"


def test_route_table_is_fully_covered(world):
    """Adding an id-taking route without adding it to the attack table fails here."""
    alice, _, a, _ = world
    covered = {(m, re.sub(r"[0-9a-f]{12}", "{id}", p)) for m, p, _ in _id_routes(a)}
    pattern = re.compile(r"\{[^}]+\}")
    wanted = set()
    for m, p in flatten_routes(alice.app.routes):
        if (
            p.startswith("/api/")
            and (pattern.search(p) or p in ("/api/sections", "/api/students"))
            and m in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        ):
            if p.startswith("/api/auth") or p in ("/api/{path:path}",):
                continue
            if p == "/api/students" and m == "GET":
                continue
            wanted.add((m, pattern.sub("{id}", p)))
    wanted -= {("GET", "/api/{path:path}")}
    assert wanted <= covered, f"id routes without a cross-tenant test: {sorted(wanted - covered)}"


# ── AI surfaces ─────────────────────────────────────────────────────────
def test_chat_context_and_tools_are_scoped(world):
    alice, _, a, b = world
    f = alice.app.state.session_factory
    with f() as db:
        owner_b = db.execute(
            __import__("sqlalchemy").text("select id from users where email='bob@example.com'")
        ).scalar()
        roster, focus = ai.build_context_parts(db, owner_b, a["students"][1])  # B asks about A's student id
        assert A_CANARY not in roster and A_NOTE not in roster and focus == ""
        for name, args in [
            ("find_students", {}),
            ("find_students", {"name_contains": "canary"}),
            ("find_students", {"section": "Algebra", "limit": 25}),
            ("get_student", {"student_id": a["students"][1]}),
            ("get_student", {"name": "ALICE"}),
            ("class_stats", {}),
            ("class_stats", {"section": "P1"}),
        ]:
            out = ai_tools.execute(db, owner_b, name, args)
            assert A_CANARY not in out and A_NOTE not in out and a["students"][1] not in out, (name, args)
        assert "No matching student" in ai_tools.execute(db, owner_b, "get_student", {"student_id": a["students"][1]})
        # overlapping name: B's own Ada resolves to B's record only
        rec = ai_tools.execute(db, owner_b, "get_student", {"name": "Ada Lovelace"})
        assert b["students"][0] in rec and a["students"][0] not in rec
        stats = json.loads(ai_tools.execute(db, owner_b, "class_stats", {"section": "Algebra"}))
        assert stats["students"] == 1 + 6  # B's Ada + the starter "Algebra I" section; never A's two


def test_tools_refuse_to_run_without_an_owner(monkeypatch):
    monkeypatch.setattr(ai, "client", lambda: FakeAI())
    with pytest.raises(ValueError, match="owner_id"):
        asyncio.run(_drain(ai.run_chat([{"role": "user", "content": "x"}], "R", "", object())))


async def _drain(gen):
    return [e async for e in gen]


def test_chat_websocket_never_shows_another_tenants_data_to_the_model(world, monkeypatch):
    _, bob, a, _ = world
    fake = FakeAI(
        [
            tool_turn("t1", "get_student", {"student_id": a["students"][1]}),
            tool_turn("t2", "find_students", {"name_contains": "canary"}),
            end_turn("done"),
        ]
    )
    monkeypatch.setattr(ai, "client", lambda: fake)
    with bob.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "tell me about the canary", "student_id": a["students"][1]})
        while ws.receive_json()["type"] not in ("done", "error"):
            pass
    results = [
        m
        for call in fake.stream_calls
        for m in call["messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
    ]
    assert results and all(A_CANARY not in json.dumps(r) and A_NOTE not in json.dumps(r) for r in results)
    system = json.dumps([call["system"] for call in fake.stream_calls])
    assert A_CANARY not in system and A_NOTE not in system and "Ada Lovelace" in system  # B's own roster only


def test_insight_cache_is_not_shared_across_owners(world, monkeypatch):
    alice, bob, a, b = world
    payload = f'{{"headline":"{A_CANARY} headline","strengths":["s"],"concerns":["c"],"suggestions":["x"]}}'
    fake = FakeAI(creates=[payload])
    monkeypatch.setattr(ai, "client", lambda: fake)
    r = alice.get(f"/api/students/{a['students'][1]}/insight")
    assert r.status_code == 200 and A_CANARY in r.text
    assert bob.get(f"/api/students/{a['students'][1]}/insight").status_code == 404
    mine = bob.get(f"/api/students/{b['students'][0]}/insight")  # B's own overlapping-name student: no cached A text
    assert A_CANARY not in mine.text


def test_parent_draft_only_for_own_students(world, monkeypatch):
    alice, bob, a, _ = world
    fake = FakeAI(creates=['{"subject":"s","body":"b"}'])
    monkeypatch.setattr(svc, "make_client", lambda: fake)
    assert (
        bob.post(
            f"/api/reports/students/{a['students'][1]}/parent-update", json={"tone": "warm"}, headers=H
        ).status_code
        == 404
    )
    assert fake.create_calls == []  # the model was never called with A's data
    assert (
        alice.post(
            f"/api/reports/students/{a['students'][1]}/parent-update", json={"tone": "warm"}, headers=H
        ).status_code
        == 200
    )


# ── CSV / import / reports ──────────────────────────────────────────────
def test_csv_and_summary_contain_only_own_students(world):
    alice, bob, a, b = world
    mine = bob.get(f"/api/reports/sections/{b['section']}/gradebook.csv").text
    assert A_CANARY not in mine and "Ada Lovelace" in mine
    assert A_CANARY in alice.get(f"/api/reports/sections/{a['section']}/gradebook.csv").text
    assert bob.get(f"/api/reports/sections/{b['section']}/summary").json()["students"] == 1


def test_import_lands_only_in_own_sections(world):
    alice, bob, _, b = world
    r = bob.post(f"/api/sections/{b['section']}/import", json={"csv": "Imported Kid,9\nAda Lovelace,9\n"}, headers=H)
    assert r.status_code == 200 and r.json()["created"] == 1  # Ada already exists in B's section; A's Ada is irrelevant
    assert "Imported Kid" not in alice.get("/api/students").text


# ── account export / delete only touch the caller ───────────────────────
def test_export_has_only_own_data_and_delete_spares_others(world):
    alice, bob, a, _ = world
    export = bob.get("/api/account/export")
    assert export.status_code == 200 and A_CANARY not in export.text and A_NOTE not in export.text
    assert "attachment" in export.headers["content-disposition"]
    assert bob.request("DELETE", "/api/account", json={"email": "bob@example.com"}, headers=H).status_code == 204
    names = {s["name"] for s in alice.get("/api/students").json()}
    assert {"Ada Lovelace", A_CANARY} <= names
    assert alice.get(f"/api/sections/{a['section']}/gradebook").status_code == 200
