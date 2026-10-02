# Performance and scale

How Super Teacher behaves as the school grows, how that was measured, and what to change. Everything below
is a number from a run on 2026-10-01, except where a row says "not measured". Reproduce with `scripts/bench.py`.

## Method

* **Machine**: AMD Ryzen 9 9950X3D2 (16 cores / 32 threads), 63 GiB RAM, WSL2 Linux 6.18, Python 3.12.14,
  SQLite 3.53.1, SQLAlchemy 2.1.1, FastAPI 0.142.2. The box is shared with other agents; during some runs
  (earlier ones in this investigation) load average was 70-90, in the final 1k/5k/20k runs it was much lower.
  The tables use the final runs. Use the **CPU p50** column (process CPU time) for comparisons; wall p95 absorbs noise.
* **Dataset** (`build_dataset`, fixed RNG seed 7): N students over 40 sections (8 courses x 5), 20 assessments per
  section (20 score rows per student, ~8% not submitted, some not yet due), 30-180 attendance
  days per student, notes on 5% of students, plus one empty "Import target" section. Bulk-inserted with
  `executemany` into a temp SQLite **file** (default DELETE journal, as in the app), then `ANALYZE`.
  1k = 20,000 scores / 103,953 attendance rows / 20 MB; 5k = 100,000 / ~520k; 20k = 400,000 / ~2.1M. Sections hold N/40 students (25 / 125 / 500).
* **Driver**: the real FastAPI app through `TestClient` in-process, `AUTH_DISABLED=true`, one process, no network.
  AI builders (`ai.build_context_parts`, `ai_tools.execute`) are called directly with a session; no Anthropic calls.
* **Per case**: probe call, warm-up (2 calls), then p50/p95 over **15 timed runs** (cases whose probe took >3 s use 5 runs,
  >20 s use 3 - stated per table), SQL statement count via a SQLAlchemy `before_cursor_execute` hook, peak Python
  memory from one extra `tracemalloc` run, response size. Import and PUT are mutating: import data is deleted between
  runs; the PUT rewrites an existing day.
* Heavy runs went through `agent-heavy-check`, in the foreground.

## Results (measured)

### 1,000 students (15 runs)

| Case | p50 ms | p95 ms | CPU p50 ms | SQL | Peak mem MB | Response |
|---|---:|---:|---:|---:|---:|---:|
| GET /overview (all) | 391.3 | 431.6 | 385.0 | 3 | 31.9 | 3.0 KB |
| GET /overview?course_id | 22.3 | 70.7 | 23.0 | 3 | 4.1 | 3.0 KB |
| GET /students (all) | 339.6 | 409.6 | 341.3 | 3 | 31.9 | 338.8 KB |
| GET /students?section_id | 5.7 | 5.9 | 5.7 | 3 | 0.8 | 8.4 KB |
| GET /students?q=nguyen | 17.5 | 66.8 | 17.6 | 3 | 3.4 | 32.6 KB |
| GET /students?risk=at_risk | 353.3 | 413.1 | 349.8 | 3 | 31.7 | 68.6 KB |
| GET /sections/{id}/gradebook | 6.6 | 8.2 | 6.5 | 5 | 0.8 | 15.0 KB |
| GET /students/{id} | 4.7 | 5.2 | 4.7 | 5 | 0.4 | 10.0 KB |
| GET /reports/sections/{id}/summary | 19.9 | 79.7 | 19.8 | 7 | 3.8 | 6.0 KB |
| GET /reports/.../gradebook.csv | 18.2 | 74.3 | 18.1 | 7 | 3.8 | 2.4 KB |
| POST /sections/{id}/import (1000 rows) | 845.5 | 906.0 | 812.4 | 24 | 59.6 | 0 |
| PUT /sections/{id}/attendance (25 marks) | 3.8 | 4.0 | 4.0 | 5 | 0.2 | 2.0 KB |
| ai.build_context_parts | 2,320.6 | 2,549.4 | 2,287.8 | 8 | 148.5 | 11.5 KB |
| ai_tools find_students | 2,218.7 | 2,846.5 | 2,206.8 | 7 | 148.2 | 3.6 KB |
| ai_tools class_stats | 2,443.5 | 2,597.2 | 2,425.3 | 7 | 148.3 | 3.2 KB |

### 5,000 students (`reports.py` fix present; roster/section cases 15 runs; AI cases 5 runs, no tracemalloc)

| Case | p50 ms | p95 ms | CPU p50 ms | SQL | Peak mem MB |
|---|---:|---:|---:|---:|---:|
| GET /overview (all) | 2,476.2 | 3,055.1 | 2,441.9 | 3 | 160.0 |
| GET /overview?course_id | 280.6 | 361.7 | 284.5 | 3 | 19.8 |
| GET /students (all) | 2,405.3 | 2,558.8 | 2,374.1 | 3 | 160.0 |
| GET /students?section_id (125) | 24.1 | 96.8 | 23.7 | 3 | 3.9 |
| GET /students?q=nguyen | 176.0 | 261.0 | 178.9 | 3 | 15.7 |
| GET /students?risk=at_risk | 2,439.6 | 2,696.1 | 2,413.5 | 3 | 160.0 |
| GET /sections/{id}/gradebook | 25.9 | 118.0 | 25.6 | 5 | 4.2 |
| GET /students/{id} | 4.7 | 5.2 | 4.7 | 5 | 0.4 |
| GET /reports/sections/{id}/summary | 291.7 | 325.3 | 287.2 | 7 | 18.9 |
| GET /reports/.../gradebook.csv | 300.4 | 337.3 | 302.3 | 7 | 18.5 |
| POST /sections/{id}/import (1000 rows) | 1,059.5 | 1,198.3 | 978.1 | 24 | 59.6 |
| PUT /sections/{id}/attendance (125 marks) | 8.2 | 13.0 | 8.5 | 5 | 0.6 |
| ai.build_context_parts | 12,039.3 | 13,305.2 | 11,946.0 | 24 | 736.4 (*) |
| ai_tools find_students | 11,628.1 | 11,912.7 | 11,537.0 | 23 | 736.5 (*) |
| ai_tools class_stats | 11,387.7 | 12,289.5 | 11,314.3 | 23 | n/a (*) |

(*) tracemalloc peak from an earlier, noisier, otherwise identical run of the same dataset; the final AI run skipped tracemalloc to bound its duration.

### 20,000 students (partial, 5 runs, 1 warm-up, no tracemalloc; sections of 500)

| Case | p50 ms | p95 ms | CPU p50 ms | SQL |
|---|---:|---:|---:|---:|
| GET /overview (all) | 8,229.3 | 8,831.7 | 8,124.7 | 3 |
| GET /students (all) | 8,664.2 | 10,032.8 | 8,552.5 | 3 |
| GET /students?section_id (500) | 111.2 | 227.8 | 110.4 | 3 |
| GET /reports/sections/{id}/summary | 1,190.1 | 1,300.5 | 1,173.8 | 7 |
| PUT /sections/{id}/attendance (500 marks) | 14.5 | 17.9 | 14.4 | 5 |

**Not measured at 20k**: the AI builders, import, gradebook and memory (a 20k AI run exceeds the 10-minute foreground
limit of a single wrapped command; I did not split it further). Extrapolating the 1k->5k AI memory ratio (5x) gives
roughly 3 GB for a 20k context build; that is an estimate, not a measurement.

## Scaling verdict

* **Linear, with a large constant.** 1k -> 5k -> 20k CPU p50 for `/overview` (all): 385 -> 2,442 -> 8,125 ms
  (6.3x for 5x data, then 3.3x for 4x). `/students` (all): 341 -> 2,374 -> 8,553 ms. AI context: 2,288 -> 11,946 ms
  (5.2x for 5x) and traced memory 148 -> 736 MB (5.0x). Statement counts are constant in N for every
  read endpoint (3-8); the exceptions are the two AI paths, whose count grows with N (8 -> 24 from 1k to 5k, see R1).
  No quadratic behaviour was found in the endpoints themselves except `class_summary` in the number of
  *assessments* (fixed in this PR, below).
* **Cost per student**: roster endpoints ~0.4-0.5 ms per student; AI context/tools ~2.3 ms per student, per call.
* **What blows up first** (with a 1 s interactive budget): the AI paths (over budget from ~400 students; at 1k a
  single chat turn spends 2.3 s building the roster before the model is even called, and each tool call costs another
  2.2-2.4 s because `ai_tools.execute` reloads everything), then unbounded `/overview` and `/students` (over 1 s from
  roughly 2k students), then CSV import (0.8-1.0 s per 1000 rows, nearly independent of database size).
* Section-scoped endpoints scale with section size, not school size: `/students?section_id` 5.7 -> 24 -> 111 ms for
  25 -> 125 -> 500 students per section.
* Single-student reads (`/students/{id}`) and the attendance PUT are flat (4.7 ms at 1k and 5k).

## Where the time goes (cProfile, 1k students, measured earlier on a loaded machine; proportions are what matter)

* **`/overview` (0.73 s profiled)**: `load_summaries` 0.71 s; of that 0.49 s is SQLAlchemy result processing, notably
  ~124k per-row `Enum` conversions for attendance (0.12 s) because every attendance row is fetched just to be counted;
  `compute_from` + `statistics.mean` ~0.13 s.
* **`ai.build_context_parts` (3.6 s profiled)**: `load_students` 2.56 s hydrating ~126k ORM objects (1.87 s in
  `loading._instance`, 125,801 `new_instance` calls), then `metrics.compute` 0.72 s (0.46 s of it in
  `statistics._exact_ratio`, the exact-fraction path of `statistics.mean`).
* **CSV import (2.46 s profiled)**: 20,000 `Score` ORM objects for 1000 students (`add_all` 1.0 s, flush/commit 1.37 s).
* **`class_summary`** (see below): 39 -> 296 -> 774 ms for 20/60/120 assessments x 300 students vs a linear
  gradebook CSV of 24 -> 73 -> 106 ms.
* At 5k, `summary` profiled: 0.30 s of 0.40 s is `load_students` ORM hydration (15.9k objects).

## Query plans (tests/test_query_plans.py)

`EXPLAIN QUERY PLAN` on the actual statements: students by section, scores by student/assessment, attendance by
student/day all use indexes (`ix_students_section_id`, `ix_scores_student_id`, `ix_attendance_student_id`, the UNIQUE
auto-indexes). Findings:

* `?q=` (`lower(name) LIKE '%x%'`) cannot use `ix_students_name`; SQLite iterates every student. Expected for a
  substring search; at 5k it costs 176 ms, at 1k 18 ms.
* On the AI path, once the roster exceeds 500 students, SQLAlchemy `selectinload` chunks its `IN (...)` lists every
  500 ids (statement count grows) and the planner walks `ix_attendance_day` (a full scan of attendance) for the 500+ id list.
  Both are encoded as **strict xfail** tests; they flip to XPASS (and fail the build, prompting marker removal) once R1 lands.
  Verified: with patch R1 applied to a scratch copy all five xfails XPASS.
* `ix_attendance_student_id` is redundant with `UNIQUE(student_id, day)`; `ix_scores_assessment_id` with `UNIQUE(assessment_id, student_id)`.

## Bug fixed in this PR

`reports.class_summary` located each student's score for each assessment with a linear scan
(`next(... for sc in s.scores if sc.assessment_id == a.id)`), i.e. O(assessments^2 x students). Fix: build one
`{assessment_id: points}` dict per student. Regression test `tests/test_reports_scaling.py` counts iterations over
`student.scores` (deterministic, fails on the old code, passes now) and compares per-assessment stats to a brute-force computation.

## Recommendations (prioritised; patches are against origin/main, `bb23101`, and were tested in a scratch copy)

Apply order: R2, R1, R3, R4, R6. Existing test-suite (111 tests) passed with all of them applied in the scratch copy.
Gains measured at **400 students** with all patches applied cumulatively in a scratch copy (paired back-to-back on a then-loaded machine, CPU p50; the ratios, not the
absolute ms, are the point) unless stated.

| # | Change | Before -> after (400 students) |
|---|---|---|
| R1 | AI paths use `load_summaries` instead of hydrating ORM graphs | ai context 1,092 -> 52 ms (21x); find_students 1,050 -> 49 ms; class_stats 1,211 -> 56 ms; memory 61 -> 5 MB; statements constant |
| R2 | Count attendance in SQL (`GROUP BY`) | overview 139 -> 44 ms (3.1x); `/students` 131 -> 62 ms; memory 13 -> 5.4 MB (all patches applied together, so the gain is not attributable to R2 alone) |
| R3 | Keyset pagination for `/students` (`limit`, `cursor`) | `/students?limit=50` 9.4 ms vs 131 ms for the full list |
| R4 | ETag / `If-None-Match` on `/overview` | a hit returns 304 before any query (verified with a write invalidating it); latency of the 304 not benchmarked |
| R5 | WAL + covering index + drop redundant indexes | covering index: attendance group-by 78.6 -> 16.0 ms (2k students, 209k rows, raw sqlite3); WAL: see contention below |
| R6 | Core bulk insert for CSV import | 1000-row import 1,407 -> 262 ms wall (cpu 1,341 -> 208 ms), statements 24 -> 5, memory 59.6 -> 22.0 MB (1k dataset) |

### Details and decisions

**Pagination contract (R3).** Keep the body a bare JSON array so existing clients keep working; page via query params and
headers. `GET /api/students?limit=1..200&cursor=<opaque>`; no `limit` = legacy full list (flip the default to 100 once the
frontend pages). Response headers `X-Total-Count` (matches ignoring `risk`; first page only) and `X-Next-Cursor` (absent on the
last page). The cursor is base64url of `[name, id]` (keyset on the existing `ORDER BY name, id`), 422 on garbage. A walk of all pages
returned exactly the unpaged list for no filter, `risk=at_risk` and `risk=watch` (checked on the demo data). Caveat: `risk` is derived
in Python, so a risk-filtered page scans forward in batches of 200 until full; fixing that needs R-later. Add an index
`ix_students_name_id (name, id)` so the keyset order needs no sort. CORS: add `expose_headers` if the SPA is ever served cross-origin.

**SQL aggregation vs Python metrics.** R2 moves only the bulk (attendance, 104k of 124k fetched rows at 1k) into SQL; the
weighted-average/trend/risk rules stay in `metrics.py` (single definition). A full move to SQL or a persisted `student_metrics`
table (refreshed in the score/attendance/import write paths) is only warranted once `risk`/average sorting and filtering must
page server-side; at the measured ~0.1 ms of Python per student after R1/R2 it is not the first thing to do. Not prototyped.

**Caching (R4).** `ETag` = per-process boot id + a counter bumped on every `Session` commit + today's date + filters
(`dataversion.py` in the patch), `Cache-Control: private, no-cache`. Valid because `cloudbuild.yaml` pins `--max-instances 1`;
with several instances use a short `max-age` instead.

**AI roster-snapshot cap (evidence).** Average `student_line` is 143.5 chars (measured, 400 students, max 150). Uncapped, the
roster would be ~143 KB at 1k, ~718 KB at 5k, ~2.9 MB at 20k - at roughly 3.7 chars per token (an approximation) that is ~39k,
~194k and ~775k tokens, i.e. beyond a 200k context from ~5k students. The existing cap (`chat_roster_cap` = 60) keeps the
snapshot at ~10.7 KB (~2.9k tokens, measured: 10,694 chars) at any size, and 11.5 KB measured at 1k. Keep the cap. The cap bounds
the *prompt*, not the *cost of building it* (2.3 s at 1k): fix that with R1. Also cache the snapshot per data version (R4's
counter) rather than rebuilding it on every chat message (`routers/ai.py` calls `build_context_parts` per turn).

**SQLite limits and Postgres.** Production is one Cloud Run instance with SQLite on a mounted volume (`--max-instances 1`).
Small contention experiment (`scripts/bench.py --contention`; 120 students, 3 s per cell, 4 reader threads, one process so GIL-limited,
machine loaded - indicative only; the 1000-student version was blocked by the heavy-check lock, exit 75):

| journal | writers | write p95 ms | read p95 ms | errors |
|---|---:|---:|---:|---:|
| DELETE (app default) | 1 | 32.9 | 2,272.6 | 0 |
| DELETE | 8 | 2,638.5 | 3,067.2 | 0 |
| WAL | 1 | 42.3 | 146.7 | 0 |
| WAL | 8 | 481.1 | 593.2 | 0 |

In the default rollback-journal mode readers wait for writers (read p95 > 2 s with a single writer present). WAL removes most of
that. No "database is locked" errors appeared because SQLAlchemy/sqlite3 wait up to 5 s by default. Caveat: WAL needs shared memory and
is not supported on NFS/GCS FUSE volumes, which `docs/DEPLOYMENT.md` lists as options; use it only on a local persistent disk.
Move to Postgres when any of these hold: more than one app instance is needed, sustained concurrent writes (attendance taken by many
teachers at once), the database no longer fits comfortably in page cache (~20 MB per 1k students here, so ~400 MB at 20k), or you need
trigram/FTS search for `q`. The code is portable (SQLAlchemy); the other session's Postgres work should reuse R2-R4 unchanged.

**Indexes (R5).** (1) `CREATE INDEX ix_attendance_student_status ON attendance(student_id, status)` makes the R2 group-by
index-only (78.6 -> 16.0 ms at 209k rows); (2) drop the two redundant indexes (after dropping them plus the new one and `VACUUM`, the 2k
dataset file was 31.4 MB, 45.8 MB with the new index and the redundant ones present); (3) `ix_students_name_id (name, id)` for R3.
Migration sketch (chain after the current head; SQLite batch mode as in `0001`):

```python
def upgrade():
    op.create_index("ix_attendance_student_status", "attendance", ["student_id", "status"])
    op.create_index("ix_students_name_id", "students", ["name", "id"])
    op.drop_index("ix_attendance_student_id", "attendance")
    op.drop_index("ix_scores_assessment_id", "scores")
```

WAL (local disk only), in `db.make_engine`'s connect hook: `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000`.
These index/pragma changes are sketches; only the covering-index timing was measured, the migration itself was not run.

### Patch R2 - attendance counted in SQL (`metrics.py`, `queries.py`)

```diff
diff --git a/superteacher/metrics.py b/superteacher/metrics.py
index 82f3dc6..6d47c5f 100644
--- a/superteacher/metrics.py
+++ b/superteacher/metrics.py
@@ -7,7 +7,8 @@ detail view, the overview and the AI context, so the numbers never disagree.
 from __future__ import annotations
 
 import hashlib
-from collections.abc import Iterable
+from collections import Counter
+from collections.abc import Iterable, Mapping
 from dataclasses import dataclass, field
 from datetime import date
 from statistics import mean
@@ -94,9 +95,15 @@ def compute(student: Student, today: date | None = None) -> StudentMetrics:
 
 
 def compute_from(
-    points: list[ScorePoint], statuses: list[AttendanceStatus], today: date | None = None
+    points: list[ScorePoint],
+    statuses: Iterable[AttendanceStatus] | Mapping[AttendanceStatus, int],
+    today: date | None = None,
 ) -> StudentMetrics:
-    """Same as :func:`compute` but over plain values, so bulk callers can skip ORM hydration."""
+    """Same as :func:`compute` but over plain values, so bulk callers can skip ORM hydration.
+
+    ``statuses`` may be the raw status list or already-aggregated ``{status: count}`` (what SQL ``GROUP BY`` returns).
+    """
+    att: Mapping[AttendanceStatus, int] = statuses if isinstance(statuses, Mapping) else Counter(statuses)
     today = today or date.today()
     m = StudentMetrics(scores=_sort(points))
     due = [s for s in m.scores if s.due_date <= today]
@@ -124,12 +131,12 @@ def compute_from(
     if hw_due:
         m.homework_rate = sum(1 for s in hw_due if s.points is not None) / len(hw_due) * 100
 
-    counted = [st for st in statuses if st is not AttendanceStatus.excused]
+    present, tardy = att.get(AttendanceStatus.present, 0), att.get(AttendanceStatus.tardy, 0)
+    counted = sum(att.values()) - att.get(AttendanceStatus.excused, 0)
     if counted:
-        attended = sum(1 for st in counted if st in (AttendanceStatus.present, AttendanceStatus.tardy))
-        m.attendance_rate = attended / len(counted) * 100
-    m.absences = sum(1 for st in statuses if st is AttendanceStatus.absent)
-    m.tardies = sum(1 for st in statuses if st is AttendanceStatus.tardy)
+        m.attendance_rate = (present + tardy) / counted * 100
+    m.absences = att.get(AttendanceStatus.absent, 0)
+    m.tardies = tardy
 
     _assess_risk(m)
     return m
diff --git a/superteacher/queries.py b/superteacher/queries.py
index 31d7ba3..bf8f70a 100644
--- a/superteacher/queries.py
+++ b/superteacher/queries.py
@@ -3,7 +3,7 @@
 Lives below both layers: it depends only on ``models`` and ``metrics``, so a service never has to import a router.
 """
 
-from sqlalchemy import select
+from sqlalchemy import func, select
 from sqlalchemy.orm import Session, joinedload, selectinload
 
 from . import metrics
@@ -58,9 +58,11 @@ def load_summaries(db: Session, **filters) -> list[tuple[Student, metrics.Studen
         .where(Score.student_id.in_(ids_q))
     ):  # fmt: skip
         points.setdefault(sid, []).append(metrics.make_point(aid, title, kind, due, mx, pts))
-    statuses: dict[str, list] = {}
-    for sid, status in db.execute(
-        select(AttendanceRecord.student_id, AttendanceRecord.status).where(AttendanceRecord.student_id.in_(ids_q))
+    att: dict[str, dict] = {}  # {student_id: {status: count}} -- aggregated in SQL, not one row per day
+    for sid, status, n in db.execute(
+        select(AttendanceRecord.student_id, AttendanceRecord.status, func.count())
+        .where(AttendanceRecord.student_id.in_(ids_q))
+        .group_by(AttendanceRecord.student_id, AttendanceRecord.status)
     ):
-        statuses.setdefault(sid, []).append(status)
-    return [(s, metrics.compute_from(points.get(s.id, []), statuses.get(s.id, []))) for s in students]
+        att.setdefault(sid, {})[status] = n
+    return [(s, metrics.compute_from(points.get(s.id, []), att.get(s.id, {}))) for s in students]
```

### Patch R1

```diff
diff --git a/superteacher/ai.py b/superteacher/ai.py
index e9710b5..fbf292c 100644
--- a/superteacher/ai.py
+++ b/superteacher/ai.py
@@ -26,7 +26,7 @@ from . import ai_tools, metrics, schemas
 from .ai_tools import clean, section_label, student_block, student_line
 from .config import get_settings
 from .models import InsightCache, Student
-from .queries import load_students
+from .queries import load_summaries
 
 log = logging.getLogger(__name__)
 
@@ -96,8 +96,9 @@ def client() -> AsyncAnthropic | None:
 def build_context_parts(db: Session, student_id: str | None = None) -> tuple[str, str]:
     """(roster snapshot, focus block). The roster part is stable across turns, so it carries the cache breakpoint."""
     cap = setting_int("chat_roster_cap", 60)
-    students = load_students(db)
-    computed = {s.id: metrics.compute(s) for s in students}
+    pairs = load_summaries(db)  # column tuples + one SQL aggregate, not a hydrated ORM graph per student
+    students = [s for s, _ in pairs]
+    computed = {s.id: m for s, m in pairs}
     out = [f"Today is {datetime.now(UTC):%Y-%m-%d}. Roster snapshot ({len(students)} students):", "<roster>"]
     if len(students) <= cap:
         out += [student_line(s, computed[s.id]) for s in students]
diff --git a/superteacher/ai_tools.py b/superteacher/ai_tools.py
index 3d439b4..147c897 100644
--- a/superteacher/ai_tools.py
+++ b/superteacher/ai_tools.py
@@ -19,7 +19,7 @@ from sqlalchemy.orm import Session
 
 from . import metrics
 from .models import Student
-from .queries import load_students
+from .queries import load_summaries
 
 MAX_TOOL_RESULT_CHARS = 12_000
 _CTRL = re.compile(r"[\x00-\x1f\x7f]+")
@@ -157,12 +157,11 @@ def _row(s: Student, m: metrics.StudentMetrics) -> dict[str, Any]:
     }  # fmt: skip
 
 
-def find_students(students: list[Student], a: FindStudentsArgs) -> dict[str, Any]:
+def find_students(pairs: list[tuple[Student, metrics.StudentMetrics]], a: FindStudentsArgs) -> dict[str, Any]:
     rows = []
-    for s in students:
+    for s, m in pairs:
         if not _in_section(s, a.section) or (a.name_contains and a.name_contains.lower() not in s.name.lower()):
             continue
-        m = metrics.compute(s)
         if a.risk and m.risk != a.risk:
             continue
         if (a.max_average is not None and (m.average is None or m.average > a.max_average)) or (
@@ -192,11 +191,11 @@ def find_students(students: list[Student], a: FindStudentsArgs) -> dict[str, Any
     }
 
 
-def get_student(students: list[Student], a: GetStudentArgs) -> dict[str, Any] | str:
+def get_student(pairs: list[tuple[Student, metrics.StudentMetrics]], a: GetStudentArgs) -> dict[str, Any] | str:
     if a.student_id:
-        hits = [s for s in students if s.id == a.student_id]
+        hits = [(s, m) for s, m in pairs if s.id == a.student_id]
     elif a.name:
-        hits = [s for s in students if a.name.lower() in s.name.lower()]
+        hits = [(s, m) for s, m in pairs if a.name.lower() in s.name.lower()]
     else:
         return {"error": "Provide student_id or name."}
     if not hits:
@@ -204,14 +203,14 @@ def get_student(students: list[Student], a: GetStudentArgs) -> dict[str, Any] |
     if len(hits) > 1:
         return {
             "error": "Several students match; call again with student_id.",
-            "candidates": [_row(s, metrics.compute(s)) for s in hits[:10]],
+            "candidates": [_row(s, m) for s, m in hits[:10]],
         }
-    s = hits[0]
-    return "<student_record>\n" + student_block(s, metrics.compute(s), max_scores=15) + "\n</student_record>"
+    s, m = hits[0]
+    return "<student_record>\n" + student_block(s, m, max_scores=15) + "\n</student_record>"
 
 
-def class_stats(students: list[Student], a: ClassStatsArgs) -> dict[str, Any]:
-    pool = [(s, metrics.compute(s)) for s in students if _in_section(s, a.section)]
+def class_stats(pairs: list[tuple[Student, metrics.StudentMetrics]], a: ClassStatsArgs) -> dict[str, Any]:
+    pool = [(s, m) for s, m in pairs if _in_section(s, a.section)]
     if not pool:
         return {"error": "No students in that section."}
 
@@ -266,7 +265,7 @@ def execute(db: Session, name: str, raw_input: object) -> str:
         raise ToolError(
             "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
         ) from None
-    result = fn(load_students(db), args)
+    result = fn(load_summaries(db), args)
     text = result if isinstance(result, str) else json.dumps(result, separators=(",", ":"), default=str)
     if len(text) > MAX_TOOL_RESULT_CHARS:
         text = text[:MAX_TOOL_RESULT_CHARS] + "\n[truncated]"
```

### Patch R3

```diff
diff --git a/superteacher/queries.py b/superteacher/queries.py
index bf8f70a..369c857 100644
--- a/superteacher/queries.py
+++ b/superteacher/queries.py
@@ -3,7 +3,7 @@
 Lives below both layers: it depends only on ``models`` and ``metrics``, so a service never has to import a router.
 """
 
-from sqlalchemy import func, select
+from sqlalchemy import func, select, tuple_
 from sqlalchemy.orm import Session, joinedload, selectinload
 
 from . import metrics
@@ -35,7 +35,13 @@ def load_students(db: Session, **filters) -> list[Student]:
     return list(db.scalars(q).unique())
 
 
-def load_summaries(db: Session, **filters) -> list[tuple[Student, metrics.StudentMetrics]]:
+def count_students(db: Session, **filters) -> int:
+    return db.scalar(_filtered(select(func.count(Student.id)).join(Section), filters)) or 0
+
+
+def load_summaries(
+    db: Session, *, limit: int | None = None, after: tuple[str, str] | None = None, **filters
+) -> list[tuple[Student, metrics.StudentMetrics]]:
     """Students plus metrics for list/overview/gradebook views.
 
     Scores and attendance are read as plain column tuples (two queries) instead of hydrating
@@ -46,10 +52,15 @@ def load_summaries(db: Session, **filters) -> list[tuple[Student, metrics.Studen
         .order_by(Student.name, Student.id),
         filters,
     )  # fmt: skip
+    if after:  # keyset ("seek") pagination on the same (name, id) order as ORDER BY: O(page), not O(offset)
+        q = q.where(tuple_(Student.name, Student.id) > tuple_(*after))
+    if limit:
+        q = q.limit(limit)
     students = list(db.scalars(q).unique())
     if not students:
         return []
-    ids_q = _filtered(select(Student.id).join(Section), filters).scalar_subquery()
+    # A page is small: bind its ids directly. Unpaged callers keep the (cheaper to send) subquery.
+    ids_q = [s.id for s in students] if limit else _filtered(select(Student.id).join(Section), filters).scalar_subquery()
     points: dict[str, list[metrics.ScorePoint]] = {}
     for sid, aid, title, kind, due, mx, pts in db.execute(
         select(Score.student_id, Assessment.id, Assessment.title, Assessment.kind, Assessment.due_date,
diff --git a/superteacher/routers/roster.py b/superteacher/routers/roster.py
index 9f6a40c..766c350 100644
--- a/superteacher/routers/roster.py
+++ b/superteacher/routers/roster.py
@@ -1,5 +1,8 @@
+import base64
+import binascii
 import csv
 import io
+import json
 
 from fastapi import APIRouter, Depends, HTTPException, Query, Response
 from sqlalchemy import delete, func, select
@@ -9,7 +12,7 @@ from sqlalchemy.orm import Session, selectinload
 from .. import metrics, schemas
 from ..db import get_db
 from ..models import Assessment, Course, Note, Score, Section, Student
-from ..queries import STUDENT_LOAD, load_summaries
+from ..queries import STUDENT_LOAD, count_students, load_summaries
 
 router = APIRouter(tags=["roster"])
 
@@ -109,16 +112,60 @@ def create_section(body: schemas.SectionIn, db: Session = Depends(get_db)):
     return section
 
 
+def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
+    if not cursor:
+        return None
+    try:
+        name, sid = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
+        return str(name), str(sid)
+    except (binascii.Error, ValueError, TypeError):
+        raise HTTPException(422, "Invalid cursor") from None
+
+
+def _encode_cursor(name: str, sid: str) -> str:
+    return base64.urlsafe_b64encode(json.dumps([name, sid]).encode()).decode().rstrip("=")
+
+
 @router.get("/students", response_model=list[schemas.StudentSummary])
 def list_students(
+    response: Response,
     q: str | None = Query(default=None, max_length=120),
     course_id: str | None = None,
     section_id: str | None = None,
     risk: str | None = Query(default=None, pattern="^(on_track|watch|at_risk)$"),
+    limit: int | None = Query(default=None, ge=1, le=200, description="Page size. Omit for the legacy full list."),
+    cursor: str | None = Query(default=None, max_length=400, description="Opaque value from X-Next-Cursor."),
     db: Session = Depends(get_db),
 ):
-    rows = load_summaries(db, q=q, course_id=course_id, section_id=section_id)
-    return [summarize(s, m) for s, m in rows if not risk or m.risk == risk]
+    """Body stays a bare JSON array (backward compatible); paging metadata travels in headers.
+
+    ``X-Total-Count``: matches for the filters (ignoring ``risk``, which is derived).
+    ``X-Next-Cursor``: pass back as ``cursor`` for the next page; absent on the last page.
+    """
+    filters = {"q": q, "course_id": course_id, "section_id": section_id}
+    after = _decode_cursor(cursor)
+    if not limit:
+        rows = load_summaries(db, after=after, **filters)
+        return [summarize(s, m) for s, m in rows if not risk or m.risk == risk]
+    if risk:
+        # risk is computed in Python, so a risk-filtered page needs the metrics of every candidate. Until it is a
+        # persisted column (R-later), scan forward in bounded batches until the page is full.
+        out, last = [], after
+        while len(out) <= limit:
+            batch = load_summaries(db, limit=200, after=last, **filters)
+            if not batch:
+                break
+            last = (batch[-1][0].name, batch[-1][0].id)
+            out += [(s, m) for s, m in batch if m.risk == risk]
+        page, more = out[:limit], len(out) > limit
+    else:
+        rows = load_summaries(db, limit=limit + 1, after=after, **filters)
+        page, more = rows[:limit], len(rows) > limit
+    if more and page:
+        response.headers["X-Next-Cursor"] = _encode_cursor(page[-1][0].name, page[-1][0].id)
+    if not after:
+        response.headers["X-Total-Count"] = str(count_students(db, **filters))
+    return [summarize(s, m) for s, m in page]
 
 
 @router.post("/students", response_model=schemas.StudentDetail, status_code=201)
```

### Patch R4

```diff
diff --git a/superteacher/routers/system.py b/superteacher/routers/system.py
index 4bf284d..c593958 100644
--- a/superteacher/routers/system.py
+++ b/superteacher/routers/system.py
@@ -1,8 +1,10 @@
-from fastapi import APIRouter, Depends
+from datetime import date
+
+from fastapi import APIRouter, Depends, Request, Response
 from sqlalchemy import text
 from sqlalchemy.orm import Session
 
-from .. import metrics, schemas
+from .. import dataversion, metrics, schemas
 from ..config import get_settings
 from ..db import get_db
 from ..queries import load_summaries
@@ -26,7 +28,19 @@ def version():
 
 
 @router.get("/overview", response_model=schemas.Overview)
-def overview(course_id: str | None = None, section_id: str | None = None, db: Session = Depends(get_db)):
+def overview(
+    request: Request,
+    response: Response,
+    course_id: str | None = None,
+    section_id: str | None = None,
+    db: Session = Depends(get_db),
+):
+    # Metrics depend on "today" (what is due) and on the data; both are in the validator.
+    etag = f'W/"{dataversion.current()}:{date.today():%Y%m%d}:{course_id}:{section_id}"'
+    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}  # no-cache = revalidate every time (cheap 304)
+    if request.headers.get("if-none-match") == etag:
+        return Response(status_code=304, headers=headers)
+    response.headers.update(headers)
     computed = load_summaries(db, course_id=course_id, section_id=section_id)
 
     bands = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
```

### Patch R6

```diff
diff --git a/superteacher/routers/roster.py b/superteacher/routers/roster.py
index 766c350..aa72c80 100644
--- a/superteacher/routers/roster.py
+++ b/superteacher/routers/roster.py
@@ -5,13 +5,13 @@ import io
 import json
 
 from fastapi import APIRouter, Depends, HTTPException, Query, Response
-from sqlalchemy import delete, func, select
+from sqlalchemy import delete, func, insert, select
 from sqlalchemy.exc import IntegrityError
 from sqlalchemy.orm import Session, selectinload
 
 from .. import metrics, schemas
 from ..db import get_db
-from ..models import Assessment, Course, Note, Score, Section, Student
+from ..models import Assessment, Course, Note, Score, Section, Student, _id
 from ..queries import STUDENT_LOAD, count_students, load_summaries
 
 router = APIRouter(tags=["roster"])
@@ -246,13 +246,14 @@ def import_students(section_id: str, body: schemas.ImportIn, db: Session = Depen
             skipped.append(f"Row {i}: {name} is already in this section")
             continue
         existing.add(name.casefold())
-        st = Student(name=name, grade_level=level, section_id=section_id)
-        db.add(st)
-        new.append(st)
+        new.append({"id": _id(), "name": name, "grade_level": level, "section_id": section_id})
         created += 1
-    db.flush()
-    if new:
-        for aid in db.scalars(select(Assessment.id).where(Assessment.section_id == section_id)).all():
-            db.add_all(Score(assessment_id=aid, student_id=st.id, points=None) for st in new)
+    if new:  # Core executemany: ~20 ORM objects per imported student (one Score per assessment) cost 2.4 s per 1000 rows
+        db.execute(insert(Student), new)
+        aids = db.scalars(select(Assessment.id).where(Assessment.section_id == section_id)).all()
+        if aids:  # an empty parameter list would execute one all-defaults INSERT
+            db.execute(
+                insert(Score), [{"assessment_id": a, "student_id": r["id"], "points": None} for r in new for a in aids]
+            )
     db.commit()
     return schemas.ImportResult(created=created, skipped=skipped)
```

Notes: R4's patch also needs the new file `superteacher/dataversion.py`:

```python
import secrets
from itertools import count

from sqlalchemy import event
from sqlalchemy.orm import Session

_BOOT = secrets.token_hex(4)  # an ETag from another process/boot can never match
_counter = count(1)
_version = next(_counter)


def current() -> str:
    return f"{_BOOT}.{_version}"


def _bump(_session) -> None:
    global _version
    _version = next(_counter)


event.listen(Session, "after_commit", _bump)
```

The R1 patch changes tool handler signatures to take `(student, metrics)` pairs; the existing tests only use the public
`execute` / `build_context_parts`, so none needed changes. Remove the three `AI_N_PLUS_ONE`/`PLAN_XFAIL` markers in
`tests/test_query_plans.py` after applying R1.

## Reproduce

```bash
python scripts/bench.py --sizes 1000 --runs 15 --json out.json --markdown out.md       # CI does this (bench-smoke, non-blocking)
python scripts/bench.py --sizes 5000 --keep-db /tmp/5k.db --reuse-db --only ai          # one case group, reuse the DB
python scripts/bench.py --sizes 1000 --runs 1 --warmup 0 --no-mem --profile /tmp/prof   # cProfile dump per case
python scripts/bench.py --sizes 1000 --contention                                       # single-writer experiment
python scripts/bench.py --merge a.json b.json --markdown merged.md
python -m pytest tests/test_query_plans.py tests/test_reports_scaling.py                # fast guards, part of the normal suite
```
