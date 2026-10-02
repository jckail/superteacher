#!/usr/bin/env python
"""Scale benchmark for Super Teacher.

Builds a deterministic synthetic school in a temp SQLite file, then drives the *real* FastAPI app
(in-process TestClient, auth disabled) and the network-free AI context builders, recording per case:
p50/p95 latency, SQL statement count, peak Python memory (tracemalloc) and response size.

    python scripts/bench.py --sizes 1000 5000 20000 --runs 15 --json out.json --markdown out.md
    python scripts/bench.py --sizes 1000 --profile /tmp/prof     # also cProfile the slowest cases

Dataset definition (per size N): 40 sections (8 courses x 5), N/40 students each, 20 assessments per
section (=> 20 score rows/student, ~8% unsubmitted), 30-180 attendance days per student, notes on 5% of
students (1-3 each). RNG seed is fixed, so row counts and values are reproducible; dates are relative to
"today" so metrics (due vs. not due) behave like production.

Nothing here makes network calls and nothing is imported by the app; it is safe to run in CI.
"""

from __future__ import annotations

import argparse
import contextlib
import cProfile
import json
import logging
import os
import platform
import pstats
import random
import resource
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://")  # never touch ./data while importing the app
os.environ.pop("ANTHROPIC_API_KEY", None)  # the benchmark must stay offline

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from superteacher import (  # noqa: E402
    ai,
    ai_tools,
    schemas,
)
from superteacher import db as database  # noqa: E402
from superteacher.calendar import school_today  # noqa: E402
from superteacher.config import get_settings  # noqa: E402
from superteacher.main import create_app  # noqa: E402
from superteacher.models import OWNER_EMAIL, OWNER_ID  # noqa: E402
from superteacher.queries import load_summaries  # noqa: E402
from superteacher.routers import attendance as attendance_router  # noqa: E402
from superteacher.routers import roster as roster_router  # noqa: E402


def _quiet_logs() -> None:  # only when run as a script: importing this module (tests) must not touch logging
    for name in ("httpx", "httpx2", "httpcore", "superteacher"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger().setLevel(logging.WARNING)


COURSES = ["Algebra", "Biology", "Chemistry", "Geometry", "History", "Literature", "Physics", "Spanish"]
SECTIONS_PER_COURSE = 5
ASSESSMENTS = 20
KINDS = ["test", "quiz", "homework", "homework", "project"]
FIRST = ["Ava", "Liam", "Maya", "Noah", "Zoe", "Ethan", "Isla", "Lucas", "Amara", "Mateo", "Priya", "Owen"]
LAST = ["Nguyen", "Patel", "Garcia", "Kim", "Okafor", "Rossi", "Haddad", "Silva", "Cohen", "Reyes", "Tanaka"]


def _id(prefix: str, i: int) -> str:
    return f"{prefix}{i:011x}"  # 12 chars, deterministic


def build_dataset(
    path: str,
    students: int,
    *,
    sections: int = 40,
    assessments: int = ASSESSMENTS,
    seed: int = 7,
    attendance_days: tuple[int, int] = (30, 180),
) -> dict:
    """Create schema (via the app's own migrations) and bulk-insert a synthetic school. Returns row counts and ids."""
    rng = random.Random(seed)
    engine = database.make_engine(f"sqlite:///{path}")
    database.run_migrations(engine)
    engine.dispose()
    today = school_today()
    con = sqlite3.connect(path)
    con.execute("PRAGMA synchronous=OFF")
    cur = con.cursor()
    courses = [
        (_id("c", i), COURSES[i % len(COURSES)] + ("" if i < len(COURSES) else f" {i}"))
        for i in range(max(1, sections // SECTIONS_PER_COURSE))
    ]
    # Every course has an owner. Passcode/auth-disabled mode (what the benchmark runs) acts as this implicit owner.
    cur.execute(
        "INSERT OR IGNORE INTO users(id,email,created_at,disabled) VALUES(?,?,?,0)",
        (OWNER_ID, OWNER_EMAIL, datetime.now(UTC).isoformat(sep=" ")),
    )
    cur.executemany(
        "INSERT INTO courses(id,name,owner_id) VALUES(?,?,?)", [(cid, name, OWNER_ID) for cid, name in courses]
    )
    secs, assess, studs, scores, att, notes = [], [], [], [], [], []
    per = students // sections
    aid_n = stid_n = scid_n = atid_n = nid_n = 0
    for si in range(sections):
        course = courses[si // SECTIONS_PER_COURSE % len(courses)]
        sec_id = _id("s", si)
        secs.append(
            (
                sec_id,
                course[0],
                f"Period {si % SECTIONS_PER_COURSE + 1}"
                + (
                    f" ({si // (SECTIONS_PER_COURSE * len(courses))})"
                    if si >= SECTIONS_PER_COURSE * len(courses)
                    else ""
                ),
            )
        )
        a_ids = []
        for k in range(assessments):
            aid = _id("a", aid_n)
            aid_n += 1
            # due dates spread from 160 days ago to 15 days ahead (a few not yet due)
            due = today - timedelta(days=160 - int(k * 175 / assessments))
            assess.append(
                (aid, sec_id, f"{KINDS[k % len(KINDS)].title()} {k + 1}", KINDS[k % len(KINDS)], 100.0, due.isoformat())
            )
            a_ids.append((aid, due))
        for _ in range(per):
            stid = _id("t", stid_n)
            studs.append((stid, f"{rng.choice(FIRST)} {rng.choice(LAST)} {stid_n:05d}", rng.randint(6, 12), sec_id))
            stid_n += 1
            ability = rng.gauss(78, 12)
            for aid, due in a_ids:
                pts = (
                    None if due > today or rng.random() < 0.08 else round(max(20, min(100, ability + rng.gauss(0, 8))))
                )
                scores.append((_id("x", scid_n), aid, stid, pts))
                scid_n += 1
            n_days = rng.randint(*attendance_days)
            presence = min(0.99, max(0.6, rng.gauss(0.92, 0.07)))
            for d in range(1, n_days + 1):
                r = rng.random()
                status = (
                    "present"
                    if r < presence
                    else "tardy"
                    if r < presence + 0.03
                    else "excused"
                    if r < presence + 0.05
                    else "absent"
                )
                att.append((_id("p", atid_n), stid, (today - timedelta(days=d)).isoformat(), status))
                atid_n += 1
            if rng.random() < 0.05:
                for _n in range(rng.randint(1, 3)):
                    notes.append(
                        (
                            _id("n", nid_n),
                            stid,
                            "Spoke with student about missing work; follow up next week.",
                            datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
                        )
                    )
                    nid_n += 1
    # An empty section with the same assessments: target of the CSV-import benchmark (cleaned between runs).
    imp = _id("s", sections)
    secs.append((imp, courses[0][0], "Import target"))
    imp_a = []
    for k in range(assessments):
        aid = _id("a", aid_n)
        aid_n += 1
        imp_a.append(aid)
        assess.append((aid, imp, f"Quiz {k + 1}", "quiz", 100.0, (today - timedelta(days=k + 1)).isoformat()))
    cur.executemany("INSERT INTO sections(id,course_id,name) VALUES(?,?,?)", secs)
    cur.executemany("INSERT INTO assessments(id,section_id,title,kind,max_points,due_date) VALUES(?,?,?,?,?,?)", assess)
    cur.executemany("INSERT INTO students(id,name,grade_level,section_id) VALUES(?,?,?,?)", studs)
    cur.executemany("INSERT INTO scores(id,assessment_id,student_id,points) VALUES(?,?,?,?)", scores)
    cur.executemany("INSERT INTO attendance(id,student_id,day,status) VALUES(?,?,?,?)", att)
    cur.executemany("INSERT INTO notes(id,student_id,body,created_at) VALUES(?,?,?,?)", notes)
    con.commit()
    cur.execute("ANALYZE")  # production-like planner statistics
    con.commit()
    con.close()
    return {
        "students": len(studs), "sections": len(secs), "assessments": len(assess), "scores": len(scores),
        "attendance": len(att), "notes": len(notes), "courses": len(courses),
        "first_section": _id("s", 0), "first_course": courses[0][0], "import_section": imp,
        "first_student": _id("t", 0), "db_bytes": os.path.getsize(path),
        "attendance_day": (today - timedelta(days=5)).isoformat(),
    }  # fmt: skip


# ── measurement ─────────────────────────────────────────────────────────
class Counter:
    def __init__(self, engine):
        self.n = 0
        self.stmts: list[str] | None = None
        event.listen(engine, "before_cursor_execute", self._hook)

    def _hook(self, conn, cursor, statement, params, context, executemany):
        self.n += 1
        if self.stmts is not None:
            self.stmts.append(statement)


def pct(sorted_vals: list[float], p: float) -> float:
    i = min(len(sorted_vals) - 1, max(0, round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def measure(
    name: str,
    fn: Callable[[], int],
    counter: Counter,
    runs: int,
    warmup: int,
    before=None,
    after=None,
    mem: bool = True,
) -> dict:
    """fn() performs one call and returns the response size in bytes. before/after run untimed."""
    for _ in range(warmup):
        if before:
            before()
        fn()
        if after:
            after()
    times, cpus, stmts, size = [], [], 0, 0
    for _ in range(runs):
        if before:
            before()
        counter.n = 0
        t0, c0 = time.perf_counter(), time.process_time()
        size = fn()
        times.append((time.perf_counter() - t0) * 1000)
        cpus.append((time.process_time() - c0) * 1000)
        stmts = max(stmts, counter.n)
        if after:
            after()
    peak = None
    if mem:  # tracemalloc slows the call 3-5x, so very heavy cases may skip it (peak RSS is still recorded)
        if before:
            before()
        tracemalloc.start()
        counter.n = 0
        fn()
        stmts = max(stmts, counter.n)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        if after:
            after()
    times.sort()
    return {
        "case": name, "runs": runs, "p50_ms": round(statistics.median(times), 1), "p95_ms": round(pct(times, 95), 1),
        "cpu_p50_ms": round(statistics.median(cpus), 1),
        "min_ms": round(times[0], 1), "max_ms": round(times[-1], 1), "sql_statements": stmts,
        "peak_mem_mb": None if peak is None else round(peak / 1e6, 1), "response_bytes": size,
        "maxrss_mb_cumulative": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }  # fmt: skip


def dataset_info(path: str) -> dict:
    """Describe an already-built benchmark database (ids are deterministic, see build_dataset)."""
    con = sqlite3.connect(path)
    n = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("students", "sections", "scores")}
    n["attendance"] = con.execute("SELECT count(*) FROM attendance").fetchone()[0]
    n["assessments"] = con.execute("SELECT count(*) FROM assessments").fetchone()[0]
    n["notes"] = con.execute("SELECT count(*) FROM notes").fetchone()[0]
    n["courses"] = con.execute("SELECT count(*) FROM courses").fetchone()[0]
    sections = n["sections"] - 1  # the extra "Import target" section
    con.close()
    return {
        **n, "first_section": _id("s", 0), "first_course": _id("c", 0), "import_section": _id("s", sections),
        "first_student": _id("t", 0), "db_bytes": os.path.getsize(path),
        "attendance_day": (school_today() - timedelta(days=5)).isoformat(),
    }  # fmt: skip


def measurement_plan(probe_seconds: float, runs: int, warmup: int, *, fixed_runs: bool = False) -> tuple[int, int]:
    """CI keeps the requested sample count; exploratory sweeps can adapt."""
    if fixed_runs or probe_seconds < 3:
        return runs, warmup
    return (max(5, runs // 3), warmup) if probe_seconds < 20 else (3, 0)


def run_size(
    n: int,
    runs: int,
    warmup: int,
    profile_dir: str | None,
    keep: str | None,
    only: list[str] | None = None,
    *,
    reuse: bool = False,
    mem: bool = True,
    paged: bool = False,
    fixed_runs: bool = False,
) -> dict:
    tmp = tempfile.mkdtemp(prefix="st-bench-")
    path = keep or os.path.join(tmp, f"bench-{n}.db")
    t0 = time.perf_counter()
    info = dataset_info(path) if reuse and os.path.exists(path) else build_dataset(path, n)
    info["build_seconds"] = round(time.perf_counter() - t0, 1)
    engine = database.make_engine(f"sqlite:///{path}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=factory, engine=engine, seed=False)

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[database.get_db] = override
    get_settings().anthropic_api_key = None
    counter = Counter(engine)
    sec, course, stu, imp, day = (
        info["first_section"],
        info["first_course"],
        info["first_student"],
        info["import_section"],
        info["attendance_day"],
    )
    results: list[dict] = []
    with TestClient(app) as c:
        # a student whose name search matches a modest number of rows (surname + digit prefix)
        def get(url: str) -> Callable[[], int]:
            def f() -> int:
                r = c.get(url)
                assert r.status_code == 200, (url, r.status_code, r.text[:200])
                return len(r.content)

            return f

        marks = [
            {"student_id": sid, "status": "present"}
            for (sid,) in sqlite3.connect(path).execute("SELECT id FROM students WHERE section_id=?", (sec,))
        ]
        counter_i = {"i": 0}

        def import_csv() -> int:
            counter_i["i"] += 1
            k = counter_i["i"]
            body = "name,grade_level\n" + "\n".join(f"Import Kid {k}-{j},{6 + j % 7}" for j in range(1000))
            r = c.post(f"/api/sections/{imp}/import", json={"csv": body})
            assert r.status_code == 200 and r.json()["created"] == 1000, r.text[:200]
            return len(r.content)

        def clean_import():
            with engine.begin() as conn:
                conn.exec_driver_sql("DELETE FROM students WHERE section_id=?", (imp,))

        def put_attendance() -> int:
            r = c.put(f"/api/sections/{sec}/attendance", json={"day": day, "marks": marks})
            assert r.status_code == 200, r.text[:200]
            return len(r.content)

        def ai_parts() -> int:
            with factory() as s:
                roster, focus = ai.build_context_parts(s, OWNER_ID, stu)
            return len(roster) + len(focus)

        def ai_tool(name: str, args: dict) -> Callable[[], int]:
            def f() -> int:
                with factory() as s:
                    return len(ai_tools.execute(s, OWNER_ID, name, args))

            return f

        cases: list[tuple[str, Callable[[], int], dict]] = [
            ("GET /overview (all)", get("/api/overview"), {}),
            ("GET /overview?course_id", get(f"/api/overview?course_id={course}"), {}),
            ("GET /students (all)", get("/api/students"), {}),
            ("GET /students?section_id", get(f"/api/students?section_id={sec}"), {}),
            ("GET /students?q=nguyen", get("/api/students?q=nguyen"), {}),
            ("GET /students?risk=at_risk", get("/api/students?risk=at_risk"), {}),
            *([("GET /students?limit=50 (paged)", get("/api/students?limit=50"), {})] if paged else []),
            ("GET /sections/{id}/gradebook", get(f"/api/sections/{sec}/gradebook"), {}),
            ("GET /students/{id}", get(f"/api/students/{stu}"), {}),
            ("GET /reports/sections/{id}/summary", get(f"/api/reports/sections/{sec}/summary"), {}),
            ("GET /reports/.../gradebook.csv", get(f"/api/reports/sections/{sec}/gradebook.csv"), {}),
            ("POST /sections/{id}/import (1000 rows)", import_csv, {"before": None, "after": clean_import}),
            ("PUT /sections/{id}/attendance", put_attendance, {}),
            ("ai.build_context_parts", ai_parts, {}),
            ("ai_tools find_students", ai_tool("find_students", {"risk": "at_risk", "sort_by": "average"}), {}),
            ("ai_tools class_stats", ai_tool("class_stats", {}), {}),
        ]
        for name, fn, kw in cases:
            if only and not any(o.lower() in name.lower() for o in only):
                continue
            # very slow cases get fewer runs so a 20k sweep stays bounded; the count used is reported.
            probe = time.perf_counter()
            fn()
            if kw.get("after"):
                kw["after"]()
            one = time.perf_counter() - probe
            r, w = measurement_plan(one, runs, warmup, fixed_runs=fixed_runs)
            res = measure(name, fn, counter, r, w, mem=mem, **kw)
            results.append(res)
            print(
                f"  [{n}] {name:42s} p50={res['p50_ms']:>9.1f} ms  p95={res['p95_ms']:>9.1f}"
                f"  cpu50={res['cpu_p50_ms']:>9.1f}"
                f"  sql={res['sql_statements']:>4}  mem={res['peak_mem_mb']} MB",
                flush=True,
            )
            if profile_dir:
                Path(profile_dir).mkdir(parents=True, exist_ok=True)
                pr = cProfile.Profile()
                pr.runcall(fn)
                if kw.get("after"):
                    kw["after"]()
                slug = "".join(ch if ch.isalnum() else "_" for ch in name)
                with (Path(profile_dir) / f"{n}_{slug}.txt").open("w") as fh:
                    pstats.Stats(pr, stream=fh).sort_stats("cumulative").print_stats(25)
    engine.dispose()
    info["loadavg_after"] = [round(x, 1) for x in os.getloadavg()]
    info["maxrss_mb_cumulative"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 0)
    return {"size": n, "dataset": info, "results": results}


def contention(students: int, duration: float, writer_counts: list[int], readers: int) -> dict:
    """Single-writer behaviour: W attendance-PUT threads + R roster-read threads against one SQLite file.

    Run for the app's default journal mode (DELETE) and for WAL. Threads share one process (GIL), so this
    measures lock waiting/errors, not parallel CPU scaling.
    """
    import shutil
    import threading

    tmp = tempfile.mkdtemp(prefix="st-contend-")
    base = os.path.join(tmp, "base.db")
    info = build_dataset(base, students)
    n_sections = 40
    out = []
    for journal in ("delete", "wal"):
        for writers in writer_counts:
            path = os.path.join(tmp, f"{journal}-{writers}.db")
            shutil.copy(base, path)
            con = sqlite3.connect(path)
            con.execute(f"PRAGMA journal_mode={journal}")
            con.close()
            engine = database.make_engine(f"sqlite:///{path}")
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            ids = {}
            for i in range(n_sections):
                sec = _id("s", i)
                rows = sqlite3.connect(path).execute("SELECT id FROM students WHERE section_id=?", (sec,)).fetchall()
                ids[sec] = [{"student_id": r[0], "status": "present"} for r in rows]
            stop = time.perf_counter() + duration
            stats = {"w": {"lat": [], "err": 0}, "r": {"lat": [], "err": 0}}
            lock = threading.Lock()

            def work(kind: str, k: int, factory=factory, stop=stop, stats=stats, lock=lock, ids=ids):
                # Router/query functions are called directly (one session per call, exactly like get_db), so the
                # threads exercise SQLite's locking without the TestClient portal (not safe to share/thread).
                sec = _id("s", k % n_sections)
                day = date.fromisoformat(info["attendance_day"])
                i = 0
                while time.perf_counter() < stop:
                    i += 1
                    t0 = time.perf_counter()
                    try:
                        with factory() as db:
                            if kind == "w":
                                status = "present" if i % 2 else "tardy"
                                body = schemas.AttendanceIn(
                                    day=day, marks=[{"student_id": m["student_id"], "status": status} for m in ids[sec]]
                                )
                                attendance_router.put_sheet(sec, body, db)
                            else:
                                rows = load_summaries(db, section_id=sec)
                                _ = [roster_router.summarize(st, m) for st, m in rows]
                        ok = True
                    except Exception as exc:  # e.g. sqlite3.OperationalError: database is locked
                        ok = False
                        with lock:
                            stats[kind].setdefault("first_error", f"{type(exc).__name__}: {str(exc)[:120]}")
                    dt = (time.perf_counter() - t0) * 1000
                    with lock:
                        if ok:
                            stats[kind]["lat"].append(dt)
                        else:
                            stats[kind]["err"] += 1

            threads = [threading.Thread(target=work, args=("w", k)) for k in range(writers)]
            threads += [threading.Thread(target=work, args=("r", 100 + k)) for k in range(readers)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            row = {"journal": journal, "writers": writers, "readers": readers, "seconds": duration}
            for kind, name in (("w", "write"), ("r", "read")):
                lat = sorted(stats[kind]["lat"])
                row[f"{name}_ops_per_s"] = round(len(lat) / duration, 1)
                row[f"{name}_p50_ms"] = round(statistics.median(lat), 1) if lat else None
                row[f"{name}_p95_ms"] = round(pct(lat, 95), 1) if lat else None
                row[f"{name}_errors"] = stats[kind]["err"]
                if stats[kind].get("first_error"):
                    row[f"{name}_first_error"] = stats[kind]["first_error"]
            out.append(row)
            print("  ", row, flush=True)
            engine.dispose()
    shutil.rmtree(tmp, ignore_errors=True)
    return {"students": students, "results": out}


def machine() -> dict:
    cpu, mem = platform.processor(), ""
    with contextlib.suppress(OSError, StopIteration):
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        cpu = next(x.split(":", 1)[1].strip() for x in lines if x.startswith("model name"))
    with contextlib.suppress(OSError, StopIteration, ValueError):
        lines = Path("/proc/meminfo").read_text().splitlines()
        mem = f"{int(next(x for x in lines if x.startswith('MemTotal')).split()[1]) / 1048576:.0f} GiB"
    import fastapi
    import sqlalchemy

    return {
        "cpu": cpu, "logical_cpus": os.cpu_count(), "ram": mem, "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version, "sqlalchemy": sqlalchemy.__version__, "fastapi": fastapi.__version__,
        "platform": platform.platform(),
    }  # fmt: skip


def markdown(report: dict) -> str:
    out = []
    m = report["machine"]
    out.append(
        f"Machine: {m['cpu']} ({m['logical_cpus']} logical), {m['ram']} RAM, Python {m['python']}, "
        f"SQLite {m['sqlite']}, SQLAlchemy {m['sqlalchemy']}\n"
    )
    for block in report["sizes"]:
        d = block["dataset"]
        out.append(
            f"### {block['size']:,} students ({d['scores']:,} scores, {d['attendance']:,} attendance rows, "
            f"DB {d['db_bytes'] / 1e6:.0f} MB)\n"
        )
        out.append("| Case | p50 ms | p95 ms | CPU p50 ms | SQL stmts | Peak mem MB | Response |")
        out.append("|---|---:|---:|---:|---:|---:|---:|")
        for r in block["results"]:
            mem = "n/a" if r["peak_mem_mb"] is None else format(r["peak_mem_mb"], ",.1f")
            out.append(
                f"| {r['case']} | {r['p50_ms']:,.1f} | {r['p95_ms']:,.1f} | {r['cpu_p50_ms']:,.1f} "
                f"| {r['sql_statements']} | {mem} | {r['response_bytes'] / 1024:,.1f} KB |"
            )
        out.append("")
    return "\n".join(out)


def main() -> None:
    _quiet_logs()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000])
    ap.add_argument("--runs", type=int, default=15, help="timed runs per case (>=15 recommended)")
    ap.add_argument(
        "--fixed-runs", action="store_true", help="keep all requested runs even for slow cases (CI budgets)"
    )
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--json", help="write JSON report here")
    ap.add_argument("--markdown", help="write markdown tables here")
    ap.add_argument("--profile", help="directory for cProfile text dumps (one per case)")
    ap.add_argument("--only", nargs="+", help="run only cases whose name contains one of these substrings")
    ap.add_argument("--contention", action="store_true", help="run the single-writer contention experiment instead")
    ap.add_argument("--keep-db", help="path of the generated DB (kept; with --reuse-db an existing one is reused)")
    ap.add_argument("--reuse-db", action="store_true", help="skip generation when --keep-db already exists")
    ap.add_argument("--no-mem", action="store_true", help="skip the tracemalloc pass (for multi-minute cases)")
    ap.add_argument("--paged", action="store_true", help="also measure GET /students?limit=50 (needs the paging patch)")
    ap.add_argument("--merge", nargs="+", help="merge JSON reports (same machine) and print/write the markdown")
    a = ap.parse_args()
    if a.merge:
        merged: dict = {}
        for f in a.merge:
            rep = json.loads(Path(f).read_text())
            if not merged:
                merged = {**rep, "sizes": []}
            for blk in rep["sizes"]:
                tgt = next((b for b in merged["sizes"] if b["size"] == blk["size"]), None)
                if tgt is None:
                    merged["sizes"].append(blk)
                else:
                    have = {r["case"] for r in tgt["results"]}
                    tgt["results"] += [r for r in blk["results"] if r["case"] not in have]
        if a.json:
            Path(a.json).write_text(json.dumps(merged, indent=2))
        md = markdown(merged)
        if a.markdown:
            Path(a.markdown).write_text(md)
        print(md)
        return
    report = {
        "machine": machine(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "runs": a.runs,
        "warmup": a.warmup,
        "sizes": [],
    }
    if a.contention:
        report["contention"] = contention(a.sizes[0], 8.0, [1, 4, 8], 4)
        if a.json:
            Path(a.json).write_text(json.dumps(report, indent=2))
        return
    for n in a.sizes:
        print(f"== {n} students", flush=True)
        report["sizes"].append(
            run_size(
                n,
                a.runs,
                a.warmup,
                a.profile,
                a.keep_db,
                a.only,
                reuse=a.reuse_db,
                mem=not a.no_mem,
                paged=a.paged,
                fixed_runs=a.fixed_runs,
            )
        )
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2))
    md = markdown(report)
    if a.markdown:
        Path(a.markdown).write_text(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
