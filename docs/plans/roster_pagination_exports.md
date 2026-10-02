# Roster API pagination and large exports

Verified against native source at HEAD `881a2af`, 2026-10-02. This is a bounded
implementation plan, not an implementation or performance result. The shared
Graphify CLI query returned no Superteacher runtime source coverage; findings
were checked against live native source. No private data, tests, builds, browser,
cloud calls, installs or graph refresh were used in this assessment.

## Reports, evaluation and keyboard focus integration (2026-10-02)

Reviewed Reports draft settlement is integrated locally as `890658e` (isolated
`47f5b4f`). Root established RED: unchanged control passed, pending teacher edits
were overwritten. The fix retains current raw subject/message/source and presents
one generated alternative for explicit review, replacement or discard. Copy/email
use the current draft; explicit actions return keyboard focus to Subject. Late
request completion leaves focus alone and cannot reach a new student/tone/section
or authenticated lifecycle. Independent task and complete-branch reviews approve
SPEC/QUALITY. Root final focused checks passed 71 tests across five files in
8.26s, types/lint/diff; combined integration passed 40 tests across three files
in 8.31s and TypeScript. Published source `11249217e32bd299179d930a2e252ecf0f0e9cb4` passed exact
[CI37043235047](https://github.com/jckail/superteacher/actions/runs/37043235047):
all seven jobs succeeded, including 1399 API tests in 186.91s, 342 web tests
across 27 files, four browser tests in 14.2s, 84 E2E tests in 1.5 minutes and
259 locked Docker cases in 33.89s; lint/types/build/benchmark passed. Root
captured actual metadata/full private logs; CI-state SHA256 is
`ad2c5e0216857cac3046a1bba9d08d17e7b16ba6718ec37023eec08ab11f57a0`.
Independent immutable archive/context/helper review and root validate passed.
Archive SHA256 `2d2e3b3d97ba7844a8f724f93bd9f4ff7fe205d3f6418a9b833d0c8321b73690`
contains 323 entries/294 files with reviewed modes. Protected build session56016
exited75 before the helper began: no intent, image or cloud mutation exists.
Preserve its private blocker and do not retry unchanged. Runtime acceptance remains
pending; source CI does not establish a deployed image.

Reviewed PR69 offline evaluator (`90a849f`) and PR70 export focus (`241939f`) are
also integrated locally. Each head passed independent review and all seven CI
jobs. The evaluator's bounded lexical replay and private hashed reports require
human semantic review; no real-model acceptance is claimed. Root ran the checked-in
synthetic example successfully without database/provider calls. Account export
restores focus synchronously before closing its popover, with no late completion
focus theft; root's two component tests passed. Broader real assistive-technology
and provider/privacy/factuality acceptance remain open.

Earlier published notes/demo/admin candidate `1f783001b81899e42ccdc388eb0a65f1bb20e2c7`
passed exact [CI37040671313](https://github.com/jckail/superteacher/actions/runs/37040671313):
1382 API tests in 194.32s, 309 web tests across 25 files, four browser tests in
14.4s, 84 E2E tests in 2.1 minutes, and 259 locked Docker cases in 36.73s;
lint/types/build/benchmark passed. Its immutable archive/context/build helper
was independently approved and actual CI proof captured; no Cloud Build or
runtime deployment was executed for that intermediate source. Build the settled
latest combined candidate after its own exact CI instead.

The latest root staging snapshot records fe2 `00009-bcw`, preserved with its
qualified receipts/original feature failure. A separate create-only private
candidate is being prepared. Root read-only preflight established operator
create/read/invoke permissions, exact runtime actAs, no project public invocation
binding, no parent reported by project GET, and a usable user developer ID-token
route. Exact-SA ID-token mint permission was not returned; no IAM grant was added.
The developer token is not established as service-audience-restricted. Actual
new-service no-token denial/token handshake, configuration, synthetic workflows
and restore still require execution. No candidate service was created by these
probes. Preserve all prior queue75 and failure receipts without unchanged retries.

Shared Graphify refreshed successfully (164506 nodes) but excludes native
Superteacher source. Canonical code-context indexing completed under its internal shared gate
(session55212): 201 files, 1744 chunks, no warnings. Semantic ParentComposer/Insight
and keyword evaluator/Attendance lookups returned correct current paths; five
changed source files match their indexed SHA256s. Sibling indexes remain absent;
earlier notes index75 was not retried. Semantic CLI and live text discovery work;
Codemogger/LSP MCP are absent from this session and Toolport profile. Agent Hub
has no configured project scope. AgentMon gateway discovery returned no tools;
its dashboard responded200 but registration/heartbeat/feed were not performed. Curated local/Git checkpoints preserve these gaps.
PR69 later advanced to reviewed `2582d8c` (typographic-apostrophe normalization
and scorer hashes); its exact CI passed, but frozen112 contains original90 only.
That nonurgent delta remains a separate integration batch; PR70 is merged.
Remaining priorities: Attendance scoped Insight/summary invalidation; independent
artifact input-day/timestamps/prompt versions; full grading policies; native
production adoption/drain/rollback/domain cutover; dedicated IAM and real
provider/email acceptance; bounded account CLI list output.

## Pre-implementation bounds and remaining materialization (881a2af)

| Surface | Verified behavior | Remaining cost |
| --- | --- | --- |
| GET /students | roster.py:list_students uses iter_summaries, then returns a complete list, including derived risk filtering | All matching summaries, validation and JSON materialize |
| queries.py:iter_summaries/summaries_for | Metadata partition size defaults to 200; history fetch yield_per=1000; owner/course/section filters apply | No roster SQL LIMIT. Complete points/status lists for each batch accumulate before metrics computation. One student's long history remains unbounded; retain_scores=False clears results after computation |
| AI tools | student_candidates SQL LIMIT 10; find_students retains at most 25 ranked results | Ranking/counting still scans relevant summaries/history; bounded output does not mean bounded CPU |
| Roster.tsx | Displays 50 rows after downloading, filtering and sorting the complete scoped array | Local pagination does not reduce HTTP, server work or browser memory |
| Student detail/prior grades | Owner/student scoped; STUDENT_LOAD hydrates history, detail loads notes; grade-history accumulates old-section score lists | Roster pagination cannot bound one student's histories |
| Overview/gradebook/attendance/class summary | Overview materializes tuples and sorts flagged students; gradebook load_summaries returns full matrix; attendance full section sheet; report summary load_students hydrates full ORM histories | Separate full HTTP representations remain |
| CSV | reports router load_students -> reports.gradebook_csv uses StringIO -> Response prepends BOM | Full student scores/assessments/attendance ORM input, complete CSV string and encoding |
| Account JSON | account.py:export_account builds nested courses/sections/students/histories/notes/insights and json.dumps(indent=2) | Full document and serialization coexist; many per-student queries |
| Browser account download | api.ts:downloadFile uses response.blob(), checks session generation before saving | Complete file buffering; no AbortSignal parameter today |
| PDF | Targeted search found no PDF runtime/router/library/UI download path | Do not claim PDF optimization or introduce a PDF feature in this slice |

Existing linear report lookup improvements and bounded query counts do not prove
bounded fetched rows, serialization or memory.

## Interface preflight matrix

| Contract | Required preservation / decision | Source |
| --- | --- | --- |
| Legacy /students | list[StudentSummary], raw SQL Student.name then Student.id order, existing q/risk/course/section behavior | roster.py, queries.py, Reports.tsx parent-update picker |
| Browser search | trim, JavaScript Unicode toLowerCase, literal substring of name only | Roster.tsx; differs from SQLite ILIKE and potentially Python/PostgreSQL lower for some Unicode |
| Browser sorts | lowercased name; raw concatenation course + space + section; numeric average/trend/attendance_rate/homework_rate; risk at_risk,watch,unknown,on_track | Roster.tsx |
| Ties/nulls | Stable JS sort preserves incoming raw SQL name/id order for equal keys; nulls last in either direction; zero is real data | Roster.tsx, metrics.py |
| Page/URL | q/status/sort/dir/page restoration; exact counts/page count; filter reset; scoped query cancellation | Roster.tsx, Roster.test.tsx, seeded roster-filters |
| Grade/calendar | One school_today as_of; active-section grades; due-only metric influence; future attendance excluded; zero/null and unknown distinct | queries.py, metrics.py, calendar/transfer/risk tests |
| Tenancy | current_user each request; SQL Course.owner_id before candidates; foreign/unknown explicit IDs indistinguishable | _scoped, owned_* |
| Exports | Existing JSON hierarchy/history scope, CSV BOM/CRLF/quoting/formula protection/blanks, filenames/media/no-store | account.py, reports.py, export/tenancy tests |
| Cancellation | api<T> accepts signal; downloadFile does not; fetch abort does not prove sync server work stops | api.ts, db.py:get_db |
| SQL dialect | SQLite lower ASCII/collation and PostgreSQL lower/collation differ; Python lower UDF exists for SQLite tool filters only | _tool_filters; PostgreSQL tests |

Do not claim a SQL metadata fast path preserves current browser Unicode search
or global ordering without explicit equivalence fixtures and dialect checks.
The current inline roster comparator does not use localeCompare; any future
localeCompare/collation change likewise needs an explicit contract.

## Task 1: additive cursor API, preserve current clients

Implement a single backend slice: authenticated GET `/students/page`, registered
before `/students/{student_id}`. Existing array endpoints and all clients stay
compatible. No claim of improved UI pagination until the client actually uses it.

Contract inputs: limit default 50, range 1..200; cursor in the
`X-Roster-Cursor` request header; q max 120; course_id;
section_id; existing four-state risk; sort name/section/average/trend/
attendance_rate/homework_rate/risk; dir asc/desc. Envelope: items,
next_cursor|null, as_of, total_matches, total_scoped. Items retain StudentSummary
without scores/attendance/notes. New default risk ascending matches browser
priority, but the additive API documents its own deterministic server order
before migration; it must not imply automatic Unicode equivalence.

Define one comparison contract: primary risk rank or unrounded numeric/string
value, null last in both directions, followed by raw name/id ascending regardless
of direction. Python-lower literal name search and string comparisons can be the
new server contract; mark remaining JS/dialect edge differences and resolve them
before replacing the client's behavior. Do not silently change legacy q ILIKE.

Fix as_of on page one, bind it into continuation and pass today explicitly to
iter_summaries/summaries_for. Preserve metrics.compute_from; no new grading/risk
formula. Apply SQL owner/course/section filters first. Reuse bounded student
metadata/history iteration; perform remaining predicates with the documented
server semantics. For derived filters/sorts, scan owner-scoped summaries and
retain only the best limit+1 items strictly after the complete cursor key. Reuse
the AI tool bounded-selection pattern, not its rounding, text cleaning, row cap
or comparator. Accumulate exact counts without retaining complete lists.

Cursor payload: version/purpose, authenticated owner, normalized query identity,
limit, as_of and full comparison key (null rank, unrounded primary value, raw
name, ID). ID alone or ordinal is insufficient. Use the already-installed
itsdangerous signing mechanism with a dedicated purpose/salt and application-held
key. Coordinate any narrow AuthState signing accessor with root; do not read
secret files, reuse cookie payloads, add infrastructure, config or dependencies.
Signing is not encryption: tokens can carry owned names. Put continuation in
`X-Roster-Cursor`, never a query parameter, next URL, browser history or persistent
storage. Application access logging omits raw queries, but Cloud Logging
[HttpRequest.requestUrl](https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry)
includes the query portion. A header avoids adding cursor names to platform URL
logs. Do not echo/log the header. Live SQL scope is always authoritative.

Bound encoded size before parsing; validate signature/version/purpose, owner,
filters/sort/limit, date/key types and finite numeric values. Generic 400 invalid
continuation for malformed/oversized/tampered/unsupported/mismatched cursors;
do not echo tokens or look up foreign anchor IDs. Ordinary query validation stays
422. Token does not authorize a read; current_user and ownership apply each time.
No new cursor-expiry policy: key rotation/version changes can require restart.

Pages are live reads with a fixed calendar cutoff, not a database snapshot.
Unchanged fixtures traverse once. Deleted anchors still work from stored keys.
Insert/delete, rename, transfer or changed metrics can move rows and cause
repeat/omission or count changes. Refresh restarts; do not promise snapshot
consistency or invent a mutation-epoch store.

Close query results/session on completion/error. The non-streaming sync endpoint
does not establish disconnect-driven server cancellation. Later React Query
consumers must forward AbortSignal and prevent stale scope/filter/session data
from becoming current.

### Cursor versus numbered pages and cost

Numbered offset envelopes preserve current deep-linked page numbers and page
counts more directly. Python derived global ranking usually retains offset+limit
rows or all results, while SQL offset also grows in cost. Cursor ranking can keep
result retention at limit+1 without new storage. Base64 alone cannot prevent
tampering or cross-owner reuse.

Task 1 keeps existing clients compatible; it does not yet preserve their future
navigation implementation. Before migrating, explicitly choose an adapter that
preserves numbered URLs or review a cursor-navigation change. Never locally
filter/sort one page as if it were the whole roster, nor preload every page to
reconstruct the old array and call it bounded loading.

Derived risk and global metric/default risk sorts still scan all relevant
histories per request, even for an empty result. JSON/ranking bounds do not bound
CPU, scanned SQL rows, individual history or all application memory. A SQL LIMIT
limit+1 fast path is valid only when filter/order/count requirements can be
satisfied without deriving excluded rows and Unicode/collation equivalence is
proved. Default risk sorting is not that path. Do not add caches, approximate
risk, stored summaries or duplicate SQL grading formulas for this first slice.

### Owned files / minimum dependencies

- superteacher/queries.py: scoped iterator reuse and bounded selection.
- superteacher/schemas.py: envelope and validated sort literals.
- superteacher/routers/roster.py: static endpoint and mapping.
- NEW superteacher/roster_pagination.py: comparator/normalization/token codec.
- NEW tests/test_roster_pagination.py: synthetic acceptance.

auth.py signing accessor is conditional coordinated overlap, not blanket
ownership. No frontend/export edits, migrations, raw-record rewrites or new
pip/npm dependencies. Existing course-owner, student-name and student-section
indexes are present. Inspect plans before any index migration; a justified later
index revision must validate SQLite/PostgreSQL separately.

## Meaningful synthetic acceptance

Use isolated fixtures with thousands of owned students plus a large foreign
roster, duplicate/case-varied/Unicode names, literal %/_/backslash, multiple
sections/courses, zero/null grades, long individual histories, transfers,
future/due scores/attendance and all four risk states. No private fixtures.

1. Concatenated unchanged pages equal a complete reference under the new explicit
   comparator for all filters/sorts/directions; ties/nulls/zero/counts/final and
   empty pages are correct. Compare client semantics separately for Unicode edge
   cases rather than assert equivalence without evidence.
2. Metrics match existing pure/ORM results at the same as_of, including school
   midnight continuation, weighted averages, due-null test/homework differences,
   active versus historical grades and future attendance exclusion.
3. Foreign scopes/cursors cannot leak foreign names, notes or insights in JSON,
   tokens, errors or captured logs. Owner/filter/limit/order changes, bad
   signature/version, malformed/oversized/non-finite keys fail generically.
4. Where a metadata fast path is actually implemented, instrument explicit LIMIT,
   fetched student rows <= limit+1 and history student IDs limited to candidates.
   Derived paths instead prove bounded ranking retention and no ORM history
   hydration, and report full scanned rows/history separately. Query count is
   insufficient. SQL execution can scan more than returned rows even with LIMIT.
5. JSON items <= limit; size tracks page size. Measure fixed-limit peak memory
   across roster sizes and independently a single long-history student. Record
   batch/history costs; avoid machine-dependent latency thresholds in CI.
6. Mutation tests cover deleted anchor, equal-name insert, rename, transfer and
   changed metrics; verify documented live semantics and owner scoping, not an
   invented snapshot guarantee. Restart refresh is deterministic.
7. Existing /students list, detail, report picker/download behavior remains.
   Static route resolves correctly. Focused pytest/lint first; root owns broad
   verification after integration. Inspect same-repo jobs and use
   agent-heavy-check for expensive checks; do not compete with auth/CI work.

## Later slices required for original scope

### Client migration, after interface review

Own web/src/types.ts, pages/Roster.tsx, test/Roster.test.tsx,
test/RosterWrite.test.tsx and e2e/seeded/roster-filters.spec.ts; api.ts only if a
shared adapter is needed. Query identity includes scope/search/risk/sort/dir/
as_of/continuation. Abort superseded requests; reset page/continuation on filters,
scope or mutation. Preserve links, empty-versus-unknown, exact match/scoped counts,
all sort buttons, URL/back/refresh behavior and mutation invalidation. Resolve
numbered navigation and Unicode equivalence before replacing full-array code.
Reports.tsx picker needs its own selection-preserving migration; legacy array
compatibility is intentional meanwhile.

### CSV streaming, independent of cursor ranking

Own routers/reports.py, CSV functions in reports.py, scoped CSV query helpers in
queries.py (coordinate ownership), tests/test_reports.py and NEW
tests/test_export_streaming.py. Read owned section/assessment metadata once and
student name/id batches with active score columns. Avoid section-wide attendance
and ORM histories; reuse metrics for averages and raw score columns for cells.
Preserve assessment due_date/title ordering including ties, as_of, zero/blank,
formula protection, escaping/CRLF and single BOM. Emit bounded CSV chunks with
StreamingResponse; header/row width still scales with assessment count. Foreign
and unknown section 404 must occur before response headers.

Resolve session lifetime against installed FastAPI dependency cleanup behavior:
db.py yields a request session today. An iterator-owned session from app factory
may be necessary. Authenticate/authorize before streaming; close result/session
in finally on disconnect/error, without detached ORM objects. After bytes start,
errors cannot become a clean JSON error; test cleanup/truncated failures and
avoid claiming a completed download. Slow readers still hold resources unless
explicitly released. Use no new queue/storage/provider.

### Account JSON streaming, separate export task

Own routers/account.py, NEW account_export.py, tests/test_accounts_tenancy.py and
NEW focused export tests. Stream existing JSON hierarchy/delimiters and individual
column records without per-student history lists or a complete document. Student
batching alone does not bound long histories. Preserve owned old-section score
history, insights, notes, empty arrays/null, dates and no-store/filename. Every
subtree query stays owner-qualified; never export auth sessions/tokens/secrets or
foreign history courses. Prove parsed schema equality on synthetic reference,
bounded fetch/chunks and controlled query growth, ordering/ties and two-owner
canaries. Whitespace change is acceptable only with schema-equivalence evidence.
Use deliberate session/disconnect/error cleanup as for CSV.

Server streaming leaves response.blob browser buffering intact. Evaluate any
native-download change against downloadFile's current session-generation
guarantee; do not silently lose that check. AbortSignal addition requires caller
ownership and cancellation tests. No PDF runtime is established; revisit only
if a real existing requirement/path appears, rather than add a PDF feature here.

## Execution checkpoint (2026-10-02)

The additive backend is committed as `4ad8c5b`, with independent spec/quality
approval. Acceptance includes varied metric/section ordering and changed-metric
live reads; 110 existing focused regression cases also passed.
CSV streaming is implemented and independently approved after fixes for active
synchronous iteration, repeated cancellation and a terminal cancelled cleanup
task. The response joins serialized cleanup before exiting. Root ran the combined
pagination/CSV acceptance suite: 67 passed, including 56 pagination and 11 CSV
cases. These are local focused results, not broad CI or deployed behavior.

Client navigation decision: migrate the roster to Previous/Next with a transient
in-memory cursor stack. Preserve scope/filter/sort URLs; normalize a legacy
numbered `page` link to the first page with an explicit restart notice. Refresh
starts a new traversal. Do not walk all preceding pages, preload the roster,
persist cursors, or put them in URLs. Reset traversal after relevant mutations
and scope/filter/order changes, abort superseded requests, and retain only the
active page data rather than every downloaded page. This deliberately changes
numbered-page deep-link behavior; existing student links and filter URLs remain.

Client migration (`9504fc1`) and account JSON streaming (`464136a`) are now
implemented and independently approved. Root's post-fix frontend/session focused
run passed 50 tests; account-stream acceptance passed 12. Integrated review
identified the CORS cursor header omission; `c95d9f9` corrects it, with two focused
origin/session regressions passing. It also adds two PostgreSQL cases for real
server cursors, cross-batch reads and owned historical export data. They skipped
locally without a test database URL; CI must supply that evidence.

Exact source `3e6629c` subsequently passed
[CI36996126364](https://github.com/jckail/superteacher/actions/runs/36996126364):
1195 API cases (including real PostgreSQL), 137 web cases, four browser cases,
83 E2E cases and all release gates. Its immutable image was built and deployed
to isolated staging revision `00002-jqp`; synthetic HTTP paging, exports,
precision/history and copied-cookie logout passed. Independent replica recovery
and subsequent staging receipt readback passed, preserving history/raw precision;
see [deployment status](../DEPLOYMENT_STATUS.md) for artifact bindings.

Six read-only probes confirmed a preexisting saved-scope hydration race and
metadata-error fallback to broader owned rows. A shell-preserving readiness/error/
missing-selection fix is merged as `6f86251` and passed exact CI separately from
the pinned staging artifact. The reviewed report picker is merged as `9dc832d`:
50-row pages, one ID-based selected snapshot, draft preservation across search,
selection/request/clipboard race guards and optional section preflight before
quota/AI. Root's 85 focused frontend and 32 report backend cases passed. Its
exact CI passed 1266 API, 183 web and four browser cases, but E2E stopped on an
ambiguous legacy Student locator (32 passed, 50 did not run). Source `4f7ba66` corrected that locator without weakening assertions and added
distinct-ID/duplicate-name coverage. Exact CI, immutable build, staging smoke,
independent replica restore and receipt readback passed.

Source `07974de` replaces class-summary full ORM history/score-matrix hydration
with owner-qualified column reads and bounded student/history batches, preserving
the pure summary as an equality reference. Native metrics, exact assessment
statistics, daily counters, ordering, future work and lifetime attendance parity
passed focused regressions and real PostgreSQL nested-cursor acceptance. Exact CI
passed 1294 API/no skips or xfails, 194 web, four browser and 83 E2E cases. Its
immutable image previously served isolated staging `00005-klh`; summary/cutoff, paging and
export HTTP checks passed. Independent read-only replica restore and subsequent
staging receipt readback passed, including integrity/FKs/head `0003` and raw
history precision; consult the deployment ledger for exact artifact bindings.

Exact medians/scalar aggregates and the complete attention response still grow
with student count; one student's attendance history and assessment width remain
unbounded. At the `07974de` checkpoint Overview's top-eight retention was
the next team plan; it subsequently shipped in `c3277b4`, recorded below. Student
grade history, Gradebook/Attendance matrices and their mutation responses require
separate later contracts. Gradebook now labels its server cutoff and revalidates
on forward school days; it still returns a full matrix.
No full metric/history CPU or global
memory bound, snapshot, browser streaming download or latency guarantee is
claimed by these changes.

## Overview retention and remaining date work

Source `68a8ee5`, included in `c3277b4`, removes Overview's full retained
student/metric list and retains at most eight attention candidates. Native means
remain scalar lists and `metrics.mean_of`; literal missing-average sentinel 101
and stable raw database stream ordering are preserved. Genuine old-code retention
evidence failed at 600 live metrics, while the new reducer stays within eight
winners plus iteration temporaries. Complete native response/filter parity and
95 focused regressions passed, with independent specification and quality reviews.
No total memory/CPU/RSS or database snapshot guarantee follows.

Overview date freshness subsequently shipped in source
`b5c1b8d00294afce0ebb5228b3be1c3a423d6191`. Every Overview envelope includes its
captured server `as_of`, explicitly passed to the existing iterator. The client
displays that cutoff and refreshes the exact existing scope query on validated
forward school days, preserving readiness, cache identity, cancellation and
native reducer semantics. A bounded current-scope/day attempt resets across scope
and readiness transitions; failures/stale successes retain labeled old evidence
with manual recovery. Calendar failures never introduce a browser-date fallback.
Independent backend/client review passed.

[CI37013321634](https://github.com/jckail/superteacher/actions/runs/37013321634)
passed all seven jobs: 1312 API without skips/xfails, 207 web, four browser and
83 E2E cases. The actual Python 3.12.15 runtime compatibility set remains 259 passed.
Protected build `42d93f52-189c-43b6-a954-8e243690bda4` produced digest
`719f06c8f9da2ec4f77dcf97141e88244f4a6bdc289256c46e3f227acf5248b5`, serving isolated
staging `00007-9lq` on a fresh source-bound prefix. Synthetic HTTP and independent
recovery execution `b5c1b8d-b7l4d` (13:51:10 UTC), structured restore and subsequent
staging receipt readback passed. Exact artifact/prefix bindings are in the
[deployment ledger](../DEPLOYMENT_STATUS.md). Production services/domains are
unchanged; public Super Teacher mappings remain on `edutrack`.

Earlier published candidate `f423afcad2bfda91b9162f06457e2befee3cde7b` is pushed
to root main and the working branch. PR65 and PR66 were merged at 16:35:09 UTC.
Its exact combined [CI37034932285](https://github.com/jckail/superteacher/actions/runs/37034932285)
passed all seven jobs: 1357 API tests in 160.81s, 287 web tests across 23 files in
31.44s, four browser tests in 14.7s, 84 E2E tests in 2.1 minutes, and 259 locked
Docker compatibility cases in 35.25s; lint/types/build and informational benchmark
passed. Root captured actual metadata and full private logs. This combined run
covers the reviewed Student integration and chat-link/runbook changes; the focused
Docker set remains distinct from the full native API suite inside that image.

Immutable f423 archive SHA256
`d463c058173a68d4b81d7508eeeae0ba6e2608774f86f86dd8aecf522f65ca02`
contains 308 entries/279 files. Independent build-helper source/specification/
quality reviews passed; root validated archive/source byte agreement and the
approved 9011 substitutions in deploy/recovery/smoke helpers. Protected session
20955 completed successfully. Cloud Build `91213e75-fd3b-480a-957e-286180b77003`
accepted the exact archive and produced image digest
`8a01599ed2cb0b49f85d78bf8f9ed32289bca265236f082e69b13628a318ac25`.
Its private proof binds the actual seven-job CI state hash. Protected staging
deployment session 48075 exited 75 before its helper began; no deployment intent,
cloud mutation or f423 deployment/recovery acceptance exists. Preserve the queue
blocker and do not retry unchanged or bypass the wrapper. A fresh read-only
Cloud Run snapshot now records staging `00009-bcw` Ready at 100%, VERSION
`fe2cd01582d288346bb8f9fa565b7938ad7d24ff`, changed by another session.
The prepared B5/failed-23 state guards are stale; reconcile that ownership/state
and review new guards before any future deployment. B5 `00007-9lq` remains the
most recent root-accepted historical runtime, not the currently serving revision. This checkpoint
edit changes documentation only; source CI/artifact remain pinned to f423.

Historical 9011 checkpoint: exact source
`9011f65509e5871c8425a99ebaaa4f17b638ab34` passed all seven jobs in
[CI37028496201](https://github.com/jckail/superteacher/actions/runs/37028496201)
(1357 API in 131.56s, 225 web, four browser, 84 E2E; locked Docker 259 in 35.76s).
Reviewed Docker chmod PR63/documentation PR64 were merged and published. Archive
SHA256 `1ed2b2f022aeaf39e4f22b5aecb0f787b86fe145d8f5b154b20c29e4e4c35d26`
had 305 entries/276 files and reviewed 0644/0755 regular modes, directories 0755
and private roots 0700. Protected session 19785 exited 75 before helper execution:
no intent/proof or cloud call occurred. Preserve this blocker separately; do not
retry its unchanged action or bypass the wrapper. Fresh f423 execution follows a
distinct source/context, fresh preflight and actual lock acquisition.

Historical 1cde checkpoint: exact source
`1cde1cc24e64599fc03f6a26aad01736960764e2` passed all seven jobs in
[CI37026105054](https://github.com/jckail/superteacher/actions/runs/37026105054)
(1356 API in 182.23s, 225 web, four browser, 84 E2E; locked Docker 259 in 32.34s).
Reviewed PR19/roadmap and five-document checkpoint were integrated in `52d6433`;
that merge differed from 1cde only in documentation. Archive SHA256
`d2b7815c88bc588fe4933ddd9e2a0def0c08bf439dc0a4282991d3b7aa560353`
had 303 entries/274 files and passed source/helper/layout/mode review. Protected
session 7852 exited 75 before helper execution with no intent/proof or cloud call.
Its blocked build is separate from source23's preserved failure and queue blocker;
none establishes a new accepted runtime.

Student follow-up was integrated into the parent in commits:
`037e92f` (original isolated commit `73178da`) adds recorded-detail cutoff/
forward-day refresh, ordinary-error draft retention, fatal typed404 handling and
actual write-ordering regressions (35 new tests). `7e9b627` (original `79f85f3`)
adds captured delete-target/client/lifecycle handling (11 new cases). Both tasks
and the full branch diff have independent specification and quality approval with
no actionable findings. Original worktree:
`/home/jkail/projects/superteacher-student-freshness-20261002`.
Root-executed final focused evidence is 80 tests across eight files in 7.04s, with
types, focused lint and diff checks passing. Publication and full combined exact CI are complete at f423; staging/recovery acceptance remains pending; the immutable build is accepted. Independent Insight, generated-draft provenance and
new-after-submit note settlement remain separate. Opening note B during a pending
note-A modal has not been established as reachable; note/accessibility audits
remain ongoing, without a confirmed interaction claim from that scenario.

Earlier source23 acceptance and runtime blocker:

Reports Summary freshness subsequently passed independent review and complete
exact-source [CI37022756475](https://github.com/jckail/superteacher/actions/runs/37022756475) at `23f5ed0ff3ab2c7eddc88a027baaa5729231647c`:
1350 API, 225 web, four browser, 84 E2E and 259 Docker-runtime compatibility cases,
with all seven jobs successful. This frontend-only slice uses existing server
as_of, exact section-summary query/signal and a bounded current-section/day attempt;
old evidence/retry, selected/edited parent drafts and pending generation survive.
No formula, cursor, provider or whole-page invalidation change was introduced.

The first operator artifact built successfully but staging `00008-6cj` failed on
mode 0600 `/app/litestream.yml`. Same-archive corrected context source/mode review
passed; root's protected B build exited 75 before its helper started, with no
build-b intent/proof or cloud call. Do not retry unchanged. B5 `00007-9lq`
continues Ready at 100%; no source23 deployment/recovery acceptance is claimed.
See the deployment ledger for failure bindings and final executed proof.

Student runtime acceptance, independent Insight freshness, AI snapshot/draft semantics and paging traversal
stability require their own contracts. Roster cursors deliberately freeze the
calculation date until restart. Full grading policies/terms/enrollment and final
production adoption/drain/rollback/domain cutover remain open. Runtime IAM resources
are separately provisioned with permission probe PASS but protected rehearsal
exit 75 before execution; runtime acceptance remains pending. No total CPU/RSS
bound, atomic snapshot, zero-loss RPO or immediate-midnight freshness is claimed.
