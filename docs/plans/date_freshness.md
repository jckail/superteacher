# Date freshness: accepted behavior and locally integrated Student implementation

This checkpoint records source-verified behavior, current verification status
and locally integrated implementation awaiting publication and combined acceptance. Grading/history, paging, authentication, provider calls and
draft provenance retain their separate contracts.

## Current status

Gradebook and Overview already label calculations with the backend response
`as_of` and schedule bounded forward-school-day refreshes using the validated
calendar. Gradebook defers its automatic day read while score writes are pending;
Overview retains cached results through ordinary refresh errors. Their accepted
cutoff/freshness work is the baseline for later consumers.

Latest exact-CI-verified candidate `9011f65509e5871c8425a99ebaaa4f17b638ab34`
passed all seven exact-source jobs in
[CI37028496201](https://github.com/jckail/superteacher/actions/runs/37028496201):
1357 API tests in 131.56s, 225 web, four browser and 84 E2E tests, plus
lint/types/build, Docker/auth smoke and informational benchmark. The locked Docker
runtime compatibility set passed 259 cases in 35.76s; this is not the full native
API suite inside that image. Reviewed Docker chmod PR63 and documentation PR64
are merged into parent `9011f65`; main and the working branch are pushed.

The immutable archive SHA256
`1ed2b2f022aeaf39e4f22b5aecb0f787b86fe145d8f5b154b20c29e4e4c35d26`
contains 305 entries/276 files, with regular files 0644/0755, directories 0755 and
private roots 0700. Build-helper review passed. Protected session 19785 exited
75 before the helper began: no new intent/proof or cloud call, image digest,
deployment or restore acceptance exists. Do not retry unchanged automatically or
bypass the wrapper; future execution requires fresh capacity and preflight.
B5 `00007-9lq` remains the most recent root-accepted staging release.

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

Earlier source23 acceptance and runtime blocker:

Reports Summary freshness, initially source `6cad257`, now has complete combined
source/CI acceptance in `23f5ed0ff3ab2c7eddc88a027baaa5729231647c`:
[CI37022756475](https://github.com/jckail/superteacher/actions/runs/37022756475) passed all seven jobs (1350 API, 225 web, four browser,
84 E2E; 259 actual Docker-runtime compatibility cases). The original
`37020532918` failed a preexisting Gradebook keyboard reload/autosave barrier;
the reviewed correction waits for three distinct committed score responses before
reload without weakening original assertions. A fresh postmerge focused set passed
86 tests/types/lint after theme, clipboard feedback and table-accessibility changes.
Summary's exact section cache/signal, bounded attempt/recovery and actual edited
draft/pending-generation preservation remain verified; real provider calls are not
part of this acceptance.

There is still no accepted source23 staging runtime: its first successful immutable
build produced a candidate that failed startup on operator context mode 0600
`/app/litestream.yml`. B5 `00007-9lq` remains Ready at 100%; the independently reviewed
same-archive corrected B context passed source review, but protected build exited 75
before helper execution: no build-b intent/proof or cloud call. Do not retry unchanged.
Do not infer deployment/restore acceptance from CI or corrected script source.

Student follow-up was integrated into the parent in commits:
`037e92f` (original isolated commit `73178da`) adds recorded-detail cutoff/
forward-day refresh, ordinary-error draft retention, fatal typed404 handling and
actual write-ordering regressions (35 new tests). `7e9b627` (original `79f85f3`)
adds captured delete-target/client/lifecycle handling (11 new cases). Both tasks
and the full branch diff have independent specification and quality approval with
no actionable findings. Original worktree:
`/home/jkail/projects/superteacher-student-freshness-20261002`.
Root-executed final focused evidence is 80 tests across eight files in 7.04s, with
types, focused lint and diff checks passing. Integration is local; publication,
full combined exact CI and runtime acceptance remain pending. The 9011 CI does
not cover these new commits. Independent Insight, generated-draft provenance and
new-after-submit note settlement remain separate. Opening note B during a pending
note-A modal has not been established as reachable; note/accessibility audits
remain ongoing, without a confirmed interaction claim from that scenario.

## Locally integrated Student behavior

The integrated `Student.tsx` subscribes to the validated school calendar and retains
its exact `['student', id]` key and consumed AbortSignal. The historical `9011f65` CI does not cover
these integrated commits. Existing backend/types supply the response cutoff;
no browser-date fallback, grading formula or history contract changed.

- Same-ID cached detail/profile/note editors survive ordinary background errors
  and successful refreshes. Cold errors, typed404 and actual auth teardown remain
  distinct; typed404 hides removed/inaccessible student data and editors.
- Recorded metrics display the response `as_of`, outside independent Insight.
  Old values/cutoff remain visible during recovery, with detail Retry/manual
  refresh and separate calendar recovery.
- One transient student-ID/day attempt resets on identity change or unmount and
  marks before exact-key invalidation. Missing/error calendar, fetching/error
  detail, equal/newer cutoff and an already attempted day do not trigger a loop.
  An existing invalidated read coalesces with the calendar observation; stale
  success permits one bounded attempt and then manual recovery. No day key or
  unbounded historical identity/day map is introduced.

## Observed write ordering and integrated deletion follow-up

Actual deferred profile PATCH and detail GET regressions cover both completion
orders, transfer/grade-history grouping, failures and late aborted reads. Existing
signal cancellation/invalidation protects profile settlement; no blanket pending
write blocker was added. Actual note add/edit/delete settlement regressions remain
separate from the calendar's exact detail read and exercise captured completions.

Integrated commit `7e9b627` (original `79f85f3`) captures the delete target and its
QueryClient/lifecycle so late confirmation or completion cannot act on another
student/session. Task 2 and whole-branch specification/quality reviews approve;
publication, combined exact CI and runtime acceptance remain pending.

Existing new-note input/edit-dialog settlement policies remain separate: an input
can be edited during pending add and completion clears its current body. Opening
note B while the pending note-A modal remains active has not been established as
reachable; note settlement and accessibility audits remain ongoing. Calendar
freshness does not settle the policy for edits made after submission or provide
generated-draft provenance.

## Focused evidence and remaining publication gates

The 35 new freshness tests cover actual displayed calculations/raw points/cutoff,
empty/reopened caches, repeated polls, stale-success/manual recovery, failed reads,
calendar errors, newer cutoffs, preserved profile/new-note/edit-note drafts,
real write ordering, route A→B→A, typed404 and actual auth/transport teardown.
Day-only invalidation remains detail-scoped and does not independently refresh
Insight/history/courses/provider calls or another student. Eleven additional
cases exercise deletion targeting, captured client and lifecycle boundaries.
Compatibility includes Student edit/notes/history, calendar and authentication
fixtures. Final focused result: 80 tests/eight files in 7.04s, types/focused lint/
diff checks PASS; these are root-executed focused checks, not full exact CI.

Whole-branch final review and local integration are complete. Root must publish
the resulting candidate, run exact combined CI and verify its immutable
build/staging/recovery before runtime acceptance. The existing 9011 CI and B5
runtime do not cover the integrated Student commits. Root remains sole broad
verification and release owner.

## Remaining limits and separate contracts

The calendar polls every sixty seconds when network/runtime/background behavior
allows it. These slices provide eventual observation of a validated forward day,
not exact midnight execution or guaranteed hidden-tab/offline refresh. Never
substitute the browser's date. Backward-day/timezone-change behavior is separate;
a server cutoff newer than the observed calendar is not recomputed backwards.

Each response carries its own calculation cutoff; it is not a database row-version
snapshot across multiple requests, concurrent writers, instances or later writes.
Independent Insight is neither labeled current through the detail cutoff nor
regenerated by a calendar signal. Existing generated drafts do not gain new
provenance from metrics refresh; parent-draft provenance remains separate.

Grading terms/periods, formulas, weights, raw grades, prior-section history,
attendance policy and roster paging/cursor/export consistency contracts are
intentionally outside this slice. Do not globally invalidate paged rosters, rewrite
cursor-bound cutoffs, alter export semantics or claim atomic multi-page snapshots
as a side effect of Student freshness.
