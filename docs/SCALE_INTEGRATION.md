# Scale integration audit

Read-only audit on 2026-10-01 (America/Los_Angeles). Native source baseline:
`0344284` (`Merge security and durable persistence into TypeScript overhaul`).
The initial audit was read-only. Origin/main subsequently advanced to `6214af9` with PR 11
merged externally; the current integration combines that revision with native bounded readers.
Attendance ordering and the report lookup map are now integrated, with native-compatible tests.
No benchmark, provider call or build was run for this audit/integration.
Graphify has no usable native Superteacher coverage; findings were checked against live source and GitHub diffs.

## Reviewed revisions and verification evidence

| Source | Exact revision | Evidence |
| --- | --- | --- |
| [PR 11](https://github.com/jckail/superteacher/pull/11), `team/scale` | `6e7e3f123d150f53070b8b89cf6184a02994d19b` | GitHub diff and commit list; [CI run](https://github.com/jckail/superteacher/actions/runs/36967158474) was in progress at audit time, with lint/web passed and API/E2E/benchmark pending. |
| [PR 14](https://github.com/jckail/superteacher/pull/14), `fix/attendance-bulk-query-order` | `17e96e2ec7f095ba78f19a715038bd5066330cc0` | [CI run](https://github.com/jckail/superteacher/actions/runs/36966667719) completed successfully for that exact head: API log reports **571 passed, 6 xfailed, 2 xpassed in 57.81s**; lint, web, E2E, Docker and benchmark jobs passed. |

PR 14's description reports a local focused result of 17 passed and 2 existing xfailed.
That is author-reported evidence, distinct from the inspected CI log. Neither result verifies
integration with the native TypeScript overhaul.

PR 11 contains four commits:

- `26d27f9d86c08866b4d93b28a960153d73a0b6e0`: benchmark, query guards, report optimization and performance findings.
- `d4bbab0a9a2cc5bc7585f3875927205ac7b4bc22`: planner statistics and version-dependent expected failure adjustment.
- `a13971adf52950750e7f03cd208b99e543b98390`: PR 14 attendance ordering and chronology regression.
- `6e7e3f123d150f53070b8b89cf6184a02994d19b`: removal of the version-specific attendance expected failure.

PR 14 is already represented in current PR 11. Integrate its two-file change once, rather
than treating PR 14 and PR 11 as independent feature sets.

## Safe changes to carry forward

| File | Proposed integration | Required adaptation or check |
| --- | --- | --- |
| `superteacher/models.py` | Change `Student.attendance` ordering from day alone to `(student_id, day)`. | Keeps each student's chronological order while avoiding a globally day-ordered bulk load. Verify section CSV/summary query plans and single-student chronology on the integrated schema. No migration or index creation is part of this change. |
| `superteacher/reports.py` | In `class_summary`, create one assessment-ID-to-points dictionary per student and use dictionary lookups. | Native `class_summary` still performs a score-list scan for every assessment. Preserve `school_today()`, active-section metrics and all existing output calculations. This removes quadratic lookup cost but retains all students' score maps, so it does not bound section-report memory. |
| `tests/test_reports.py` | Add PR 14's out-of-order attendance insertion regression for bulk loading and student detail. | Use the existing school-date seam or explicit frozen day; avoid reintroducing host-local date assumptions. |
| `tests/test_reports_scaling.py` | Add deterministic score-iteration and brute-force assessment-stat checks. | Incoming `SimpleNamespace` assessment/student fixtures omit `section_id`; native `metrics.score_points` requires it to exclude prior-section grades. Supply matching active-section IDs, then include a transferred-history case. |
| `scripts/bench.py` | Optional synthetic, network-free benchmark after adapting the driver. | Use the native school calendar and migrate into a separate disposable database. Confirm report/request shapes and schema compatibility. Its module-level environment changes affect the importing process; isolate them before using it as a test fixture module. |
| `tests/test_query_plans.py` | Reuse scoped lookup/index and report-plan assertions selectively. | Replace constant-total-query assumptions with bounded-batch and scoped-history assertions. Preserve intentional full-roster metadata scans and update the AI expected failures to reflect the native architecture. |
| `.github/workflows/ci.yml` | Optional benchmark artifact job after its driver is adapted. | Add to the current workflow rather than restoring the incoming workflow. Coordinate one heavy verification owner and keep benchmark results separate from production latency claims. |

Keep native `docs/PERFORMANCE.md`; the incoming file describes an older eager-loading baseline
and several patch sketches. Put retained historical measurements in a separately labeled document
if useful, with the source revision and dataset. They cannot describe the integrated implementation.

## Architecture comparison and remaining limits

**Queries and metrics.** Native `queries.iter_summaries` streams student metadata in batches of
200; `summaries_for` reads column history and filters scores to the student's current section.
`find_students` retains at most 25 ranked results; `get_student` reads one student or at most ten
ambiguity candidates; `class_stats` accumulates exact means. Native metrics retain deterministic
same-day ordering, weighted grades, due-date rules, future-attendance exclusion and historical
as-of behavior. Incoming PR 11 only changes report lookup and attendance relationship ordering
in application code. Its R1/R2 query/metric changes are documentation patches, not shipped code.
Do not replace native bounded readers with those older list-based sketches.

**SQL counts and plans.** Native whole-roster reads intentionally use one roster query plus two
history queries per batch. Larger rosters therefore issue more statements without issuing one
statement per student. Incoming tests compare 60 and 560 students and demand equal counts;
that assertion conflicts with bounded batching for native overview, roster and AI paths.
Incoming strict AI expected failures still describe eager ORM loading; after native integration
they may fail for a different reason or unexpectedly pass. Assert scoped parameter sets, batch
bounds, no history ORM hydration and appropriate indexed history lookups instead. A full scan
of all roster metadata can be the correct plan when requesting the whole school.

**Indexes and attendance aggregation.** PR 11 adds no Alembic migration and no covering index.
Its proposed `(student_id, status)` attendance index and `(name, id)` roster index are sketches;
index drops and WAL changes are also sketches. Native file-backed SQLite already enables WAL,
`synchronous=NORMAL` and a 5-second busy timeout for Litestream. Native summaries still collect
attendance statuses for each bounded batch. A future SQL aggregation must preserve the
`day <= as_of` filter and current metrics; a covering index design must account for that date
predicate, rather than adopting historical timing claims unchanged. Inspect actual plans before
removing existing indexes.

**AI request budget.** Native `ai_capacity` implements fail-fast admission shared by chat,
insights and parent drafts on each event loop, default eight active requests. Native chat,
insight and parent operations have bounded deadlines and client cleanup; insights deduplicate
within loop/database/model/student/fingerprint and include model in cache validity. WebSocket
queues, frames and turn history are bounded, and date context freezes independently for each
turn, including threaded tools. PR 11 and PR 14 add no replacement AI admission, cancellation,
request-budget or deadline implementation. Preserve these native controls.

**Reports and history.** Native parent drafts exclude confidential teacher notes and use an
escaped student record; transfers retain prior-section raw grades for history while active
metrics exclude them. PR 11's report optimization does not change those contracts. Section
summary and CSV routes still eagerly load section students and history, and generate the full
response. Neither PR introduces pagination, output-size limits or streaming report responses.
The existing 5,000-row CSV-import limit bounds input, not report output or score rows.

**Workers and deployment.** Neither PR implements multiworker-safe global AI admission,
cross-process data-version caches or multi-instance durable SQLite. Native admission and
observability counters are process-local; total provider admission grows with worker count.
The current deployment helper pins one Cloud Run instance and uses Litestream over local
SQLite. A single instance is not itself a global admission guarantee if configured with multiple
workers. Incoming per-process ETag sketches are unsuitable for shared writes across workers;
Postgres, shared admission/cache state and identity/tenancy remain separate work. The native
512 MiB deployment memory allocation makes bounded batches valuable but is not evidence that
all large-report workloads fit.

## Proposed verification order

For the integrated PR 11 changes, verify attendance ordering and the report lookup optimization,
with their adapted regressions. Run focused report chronology/scaling and transfer-history tests,
then scoped query-plan checks on the integrated schema. Reuse existing native query-scale,
AI-tool-scale, school-calendar and capacity tests for unchanged contracts. Run one coordinated
full verification through `agent-heavy-check` after implementation settles. Benchmark separately
on disposable synthetic data only if the verification owner has resources; record revision,
calendar, dataset, query counts and peak memory. The audit provides an integration plan,
not a production-scale benchmark of the integrated changes.

## Integration validation

After origin/main PR 11 integration, adapted focused report/query/transfer tests passed:
**39 passed in 4.02s**, including 1,000-student lookup checks at 20 and 60 assessments,
missing/future grades, transferred history, school-date cutoff and chronological attendance.
The original plural report-scaling file retains the incoming 40-student/120-assessment
iteration and brute-force checks; the new singular file adds the larger synthetic and
calendar/transfer/ordering contracts. Log: `/tmp/superteacher-scale-integration-focused.log`.
These are local focused results; a new exact-commit CI run remains required.
