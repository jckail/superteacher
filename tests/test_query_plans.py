"""Query-plan and query-count guards for the hot read/write paths.

Two kinds of regression are cheap to catch here and expensive to find in production:

* a statement that stops using an index (``EXPLAIN QUERY PLAN`` shows a full ``SCAN`` of a big table);
* an endpoint that starts issuing a statement per student (N+1), i.e. its SQL count grows with data.

Datasets come from ``scripts/bench.py`` (the same generator the scale benchmark uses), at two sizes so
"constant statement count" is proven by comparison rather than asserted against a magic number alone.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from superteacher import ai, ai_tools
from superteacher import db as database
from superteacher.main import create_app

_spec = importlib.util.spec_from_file_location(
    "st_bench", Path(__file__).resolve().parent.parent / "scripts" / "bench.py"
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

SMALL, LARGE = (
    60,
    560,
)  # students; 4 sections each. LARGE > 500 on purpose: SQLAlchemy's selectinload chunks IN lists at 500
BIG_TABLES = {"students", "scores", "attendance", "notes", "assessments"}


class World:
    """One generated database + app + statement recorder."""

    def __init__(self, path: Path, students: int):
        self.info = bench.build_dataset(str(path), students, sections=4, attendance_days=(5, 15))
        self.engine = database.make_engine(f"sqlite:///{path}")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.app = create_app(session_factory=self.factory, engine=self.engine, seed=False)

        def override():
            with self.factory() as s:
                yield s

        self.app.dependency_overrides[database.get_db] = override
        with self.engine.begin() as conn:
            conn.exec_driver_sql("ANALYZE")  # planner statistics must exist regardless of SQLite version defaults
        self.statements: list[tuple[str, tuple]] = []
        event.listen(self.engine, "before_cursor_execute", self._record)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append((statement, parameters))

    def call(self, fn):
        """Run fn() and return the statements it issued."""
        self.statements.clear()
        fn()
        return list(self.statements)

    def close(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    w = World(tmp_path_factory.mktemp("small") / "s.db", SMALL)
    yield w
    w.close()


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    w = World(tmp_path_factory.mktemp("large") / "l.db", LARGE)
    yield w
    w.close()


def _ok(resp):
    assert resp.status_code == 200, resp.text[:200]
    return resp


def _actions(w: World) -> dict:
    """name -> zero-arg callable exercising one endpoint / builder against world ``w``."""
    i, c = w.info, w.client
    sec, course, stu = i["first_section"], i["first_course"], i["first_student"]
    marks = [
        {"student_id": r[0], "status": "present"}
        for r in sqlite3.connect(w.engine.url.database).execute("SELECT id FROM students WHERE section_id=?", (sec,))
    ]

    put_body = {"day": i["attendance_day"], "marks": marks}

    def ai_parts():
        with w.factory() as s:
            ai.build_context_parts(s, stu)

    def tool(name, args):
        def run():
            with w.factory() as s:
                ai_tools.execute(s, name, args)

        return run

    return {
        "overview": lambda: _ok(c.get("/api/overview")),
        "overview_course": lambda: _ok(c.get(f"/api/overview?course_id={course}")),
        "students": lambda: _ok(c.get("/api/students")),
        "students_section": lambda: _ok(c.get(f"/api/students?section_id={sec}")),
        "students_search": lambda: _ok(c.get("/api/students?q=a")),
        "gradebook": lambda: _ok(c.get(f"/api/sections/{sec}/gradebook")),
        "student_detail": lambda: _ok(c.get(f"/api/students/{stu}")),
        "summary": lambda: _ok(c.get(f"/api/reports/sections/{sec}/summary")),
        "gradebook_csv": lambda: _ok(c.get(f"/api/reports/sections/{sec}/gradebook.csv")),
        "attendance_sheet": lambda: _ok(c.get(f"/api/sections/{sec}/attendance?day={i['attendance_day']}")),
        "attendance_put": lambda: _ok(c.put(f"/api/sections/{sec}/attendance", json=put_body)),
        "ai_context": ai_parts,
        "ai_find_students": tool("find_students", {"risk": "at_risk"}),
        "ai_class_stats": tool("class_stats", {}),
    }  # fmt: skip


# Upper bound on statements per call, independent of data size. Observed values + small headroom; raise
# deliberately (with a reason) rather than let an N+1 slip in. The "same at both sizes" test below is the
# actual N+1 detector; these numbers catch a constant-factor blow-up.
BUDGET = {
    "overview": 5,
    "overview_course": 5,
    "students": 5,
    "students_section": 5,
    "students_search": 5,
    "gradebook": 7,
    "student_detail": 7,
    "summary": 9,
    "gradebook_csv": 9,
    "attendance_sheet": 5,
    "attendance_put": 8,
    "ai_context": 10,
    "ai_find_students": 10,
    "ai_class_stats": 10,
}


# Known defect (see docs/PERFORMANCE.md, recommendation R1): the AI paths call queries.load_students, whose
# selectinload(...) chunks the IN (<all student ids>) list every 500 ids, so statements grow with roster size.
# strict xfail: when the hot-file patch lands these XPASS and the marker must be deleted.
AI_N_PLUS_ONE = pytest.mark.xfail(
    strict=True, reason="load_students selectinload chunking: statements grow per 500 students"
)


def _p(name, *marks):
    return pytest.param(name, marks=marks, id=name)


@pytest.mark.parametrize("name", [_p(n, AI_N_PLUS_ONE) if n.startswith("ai_") else _p(n) for n in sorted(BUDGET)])
def test_statement_count_is_constant_in_data_size(small, large, name):
    counts = []
    for w in (small, large):
        act = _actions(w)[name]
        if name.endswith("_put"):
            act()  # first write changes rows (UPDATE); the steady-state call is what we count
        counts.append(len(w.call(act)))
    n_small, n_large = counts
    assert n_small == n_large, f"{name}: {n_small} statements at {SMALL} students vs {n_large} at {LARGE} (N+1?)"
    assert n_large <= BUDGET[name], f"{name}: {n_large} statements exceeds budget {BUDGET[name]}"


def test_import_statement_count_does_not_scale_with_rows(large):
    """CSV import must batch its inserts: 10x the rows may not mean 10x the statements."""
    sec = large.info["import_section"]

    def run(rows, tag):
        body = "name,grade_level\n" + "\n".join(f"Kid {tag}-{k},7" for k in range(rows))
        r = large.client.post(f"/api/sections/{sec}/import", json={"csv": body})
        assert r.status_code == 200 and r.json()["created"] == rows

    few = len(large.call(lambda: run(20, "a")))
    many = len(large.call(lambda: run(200, "b")))
    assert many <= few * 3, f"import issued {few} statements for 20 rows but {many} for 200"


# ── query plans ─────────────────────────────────────────────────────────
def _plans(w: World, statements):
    out = []
    with w.engine.connect() as conn:
        for sql, params in statements:
            if not sql.lstrip().upper().startswith("SELECT"):
                continue
            rows = conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, params).fetchall()
            out.append((sql, [r[3] for r in rows]))
    return out


def _full_scans(plan_rows):
    scans = []
    for row in plan_rows:
        if row.startswith("SCAN "):
            table = row.split()[1]
            # aliases from joinedload look like "sections_1"; only the big tables matter
            if table in BIG_TABLES:
                scans.append(row)
    return scans


PLAN_ACTIONS = [
    "overview", "students", "students_section", "students_search", "gradebook", "student_detail", "summary",
    "gradebook_csv", "attendance_sheet", "attendance_put", "ai_context", "ai_find_students",
]  # fmt: skip


PLAN_XFAIL = pytest.mark.xfail(
    strict=True, reason="planner walks ix_attendance_day for the 500+-id IN list of load_students (R1)"
)


def _plan_marks(n):
    if n in {"ai_context", "ai_find_students"}:
        return _p(n, PLAN_XFAIL)
    return _p(n)


@pytest.mark.parametrize("name", [_plan_marks(n) for n in PLAN_ACTIONS])
def test_no_full_scan_of_big_tables(large, name):
    stmts = large.call(_actions(large)[name])
    assert stmts, "endpoint issued no SQL?"
    plans = _plans(large, stmts)
    assert plans
    for sql, rows in plans:
        assert not _full_scans(rows), f"{name}: full table scan in plan\n{sql}\n" + "\n".join(rows)


def test_score_lookup_by_assessment_uses_index(large):
    """Per-assessment score reads/writes (PUT /assessments/{id}/scores) must not scan the scores table."""
    aid = large.engine.connect().exec_driver_sql("SELECT id FROM assessments LIMIT 1").scalar()
    with large.engine.connect() as conn:
        rows = [
            r[3] for r in conn.exec_driver_sql("EXPLAIN QUERY PLAN SELECT * FROM scores WHERE assessment_id=?", (aid,))
        ]
    assert any("ix_scores_assessment_id" in r or "autoindex_scores" in r for r in rows), rows


def test_attendance_by_student_and_day_uses_index(large):
    sid = large.engine.connect().exec_driver_sql("SELECT id FROM students LIMIT 1").scalar()
    with large.engine.connect() as conn:
        rows = [
            r[3]
            for r in conn.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT status FROM attendance WHERE student_id=? AND day=?", (sid, "2026-01-01")
            )
        ]
    assert rows and all(r.startswith("SEARCH") for r in rows), rows


def test_students_by_section_uses_index(large):
    sec = large.info["first_section"]
    with large.engine.connect() as conn:
        rows = [
            r[3] for r in conn.exec_driver_sql("EXPLAIN QUERY PLAN SELECT id FROM students WHERE section_id=?", (sec,))
        ]
    assert rows and all(r.startswith("SEARCH") for r in rows), rows
