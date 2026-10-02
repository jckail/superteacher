# Date freshness: accepted behavior and proposed Student detail slice

This checkpoint records source-verified behavior, current verification status
and proposed work. Grading/history, paging, authentication, provider calls and
draft provenance retain their separate contracts.

## Current status

Gradebook and Overview already label calculations with the backend response
`as_of` and schedule bounded forward-school-day refreshes using the validated
calendar. Gradebook defers its automatic day read while score writes are pending;
Overview retains cached results through ordinary refresh errors. Their accepted
cutoff/freshness work is the baseline for later consumers.

Reports Summary source at `6cad257` has the same bounded section/day refresh,
server-cutoff labeling, cached-data/error retention and explicit recovery controls.
Its focused verification passed 78 tests and independent specification/code-quality
review passed. Exact CI run `37020532918` failed the existing Gradebook keyboard
reload/autosave barrier; its reviewed correction now awaits combined CI. A fresh
post-merge focused set passed 86 tests, types and lint after the shared theme,
clipboard feedback and table-accessibility changes. Reports has not
been deployed on the basis of these results. A focused pass is not a full CI pass
or deployment receipt.

Student detail editor-preserving freshness remains **proposed, not implemented**.
Current [Student.tsx](../../web/src/pages/Student.tsx) reads `['student', id]`
without subscribing to the school calendar. The backend already returns one
response cutoff, and trend/attendance filters and future-versus-missing assignment
labels correctly use that cutoff. Continuously mounted derived values can remain
old until another read trigger. Its ordinary query-error early return also removes
cached profile/note editors, losing their local drafts across unmount.

## Smallest proposed Student change

Limit production changes to `web/src/pages/Student.tsx`, with a new
`web/src/test/StudentCalendar.test.tsx` and minimal calendar-fixture updates in
existing compatibility tests. Reuse [schoolCalendar.ts](../../web/src/schoolCalendar.ts)
and existing backend/types; retain the exact student key and consumed AbortSignal.

- Preserve same-ID cached detail and its profile/note editor subtree through
  ordinary background fetching/errors. Keep real typed404 behavior, cold initial
  errors and actual authentication teardown distinct. Never retain another route's
  data as fallback, key editors by cutoff, or overwrite local drafts from refreshed
  props. Existing student-ID keys already preserve drafts across successful updates.
- Label recorded metrics with the actual response `as_of`, outside the independent
  Insight card. Retain old visible values/cutoff while updating or after failure.
  Offer explicit detail Retry/manual refresh and separate calendar recovery.
- Use one transient student-ID/day attempt, reset on identity change or unmount.
  Mark before exact-key invalidation; skip missing calendar/data, fetching/errors,
  equal/newer cutoffs and a previously attempted day. Do not add day to query keys
  or retain an unbounded identity/day map.
- Wait for an existing invalidated read. A response covering the day needs no
  extra read; a stale successful response permits one bounded day attempt followed
  by manual recovery. An error retains cached editors without a refresh loop.
  One automatic attempt is distinct from existing bounded transport retries.

## Establish write ordering before selecting guards

A profile save writes a complete StudentDetail into the detail cache, then
invalidates related queries. An older GET envelope includes old section, notes
and metrics, so accepting it after transfer would overwrite the committed profile
and change the active grade-history grouping. Current TanStack invalidation uses
`cancelRefetch: true` by default and Student consumes the signal; this appears to
protect the existing sequence. Notes perform no optimistic detail write and
invalidate after their committed mutation. No reproduced overwrite has yet been
established, so a blanket pending-write blocker is not part of this proposal.

First defer genuine profile PATCH and detail GET promises under actual Student.
Advance the day during transfer; resolve PATCH before the old GET, then resolve
the cancelled GET late and the settlement GET. Assert old-read abortion, captured
student/body, one mutation, retained pending dialog/draft, correct final cache and
visible section, and correct active-section grade history. Reverse the resolution
order, cover failed saves, and repeat for real note add/edit/delete settlement.
If existing cancellation passes, add no write guard. If a failure demonstrates
pre-write acceptance, identify that ordering and add only the narrow demonstrated
student-detail protection, preserving existing mutation completion behavior.

Existing new-note input/edit-dialog settlement policies are separate: an input can
be edited during pending add and completion clears its current body; another note
can be opened while an edit is pending and completion closes editing. A calendar
read guard does not resolve those policies. Draft provenance and any policy for
new edits made after submission require separate work.

## Required future verification

The new StudentCalendar tests must assert visible values, editor state and complete
cache envelopes, not only invalidation counts:

1. A recorded future score becomes due after calendar advancement; average,
   homework/missing labels, attendance and trend change with the new response
   cutoff while raw points remain unchanged. Include empty data and reopened cache.
2. Same-day notifications do not duplicate reads; stale-success/manual recovery,
   refresh failure/Retry and unavailable-calendar recovery retain valid detail.
   A newer response cutoff never moves backwards to match an older poll.
3. Unsaved profile name/grade/section, new-note input and edit-note dialog survive
   same-ID success and ordinary failure. Pending transfer/note writes retain captured
   scope, settle once, and cannot be overwritten by late pre-write reads.
4. Route A→B→A aborts superseded reads and resets the bounded attempt; late A data
   cannot replace current data. Actual identity changes clear editor drafts;
   same-ID day updates do not. Preserve active-section history mismatch protection.
5. Cold and cached typed404 hide the removed/inaccessible student's editors without
   retrying404. Actual AuthGate/Root expiry/logout clears private state, aborts reads
   and isolates a new QueryClient from old-session read/mutation completion. Use
   actual transport/event semantics rather than a mocked401 with no expiry event.
6. Day-only refresh makes no Insight, history, course, provider or other-student
   refresh request. Existing successful profile/note mutations may still perform
   their existing Insight/history invalidations; distinguish those write requests.

Compatibility coverage: `StudentEdit.test.tsx`, `StudentNotes.test.tsx`,
`StudentHistory.test.tsx`, the Student cutoff case in `SchoolCalendar.test.tsx`,
`Auth.test.tsx` and `AuthTransport.test.tsx`. Explicitly provide a valid calendar
response in the existing Student calendar fixture. Root remains sole verification
owner; coordinate expensive checks, use the shared heavy-check wrapper where
required, and defer broader verification until changes settle.

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
