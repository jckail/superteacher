# Roster API pagination and large exports

Verified against native source at HEAD `881a2af`, 2026-10-02. This is a bounded
implementation plan, not an implementation or performance result. The shared
Graphify CLI query returned no Superteacher runtime source coverage; findings
were checked against live native source. No private data, tests, builds, browser,
cloud calls, installs or graph refresh were used in this assessment.

## Current bounds and remaining materialization

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

Contract inputs: limit default 50, range 1..200; cursor; q max 120; course_id;
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
Signing is not encryption: tokens can carry owned names, so keep them out of
logs/analytics/shareable URLs. Live SQL scope is always authoritative.

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

Next implementation: after root's current auth work, recheck live source/ownership,
review Task 1 interface/comparator/signing preflight and implement that backend
slice. Client migration, other full HTTP representations and export work remain
explicitly outstanding; pagination alone does not finish large-export memory.
