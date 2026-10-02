# Private note draft settlement

The native source permits typing in New note while its POST is pending. Its success callback currently clears the input unconditionally. A later draft can therefore be lost when the submitted note completes. This is source-supported; mounted regression execution must establish the defect before implementation.

## Required behavior

Keep typing enabled during submission. Capture the student, trimmed submitted body, local draft revision and original query client. Success clears an unchanged submitted draft, but preserves raw text after any user change, including changing away and back to the same text. Failure preserves the latest draft and reports the submitted request failure. Retain one captured POST, the existing success toast and existing scoped detail/Insight invalidations.

Same-ID day reads retain the form and revision; a real route identity change resets the keyed Notes lifecycle. A late completion cannot clear another student or new authenticated session's draft or target its query client. Do not add a generic pending-read guard, change backend note DTOs, or alter independent Insight provenance.

Pending note-edit modal switching is not an established accessible defect: the modal makes background controls inert and traps focus. Preserve that policy; do not manufacture a race by clicking inert controls or introduce an unsolicited edit lock. Profile saves, note edit/delete, Student removal and calendar contracts remain unchanged.

## Task 1: regression and implementation

A fresh producer owns the Notes add handler in `web/src/pages/Student.tsx` and a new mounted `web/src/test/StudentNoteSettlement.test.tsx`. Root owns all verification and publication.

First freeze an unchanged-draft control and two failing cases: a new raw draft typed during the pending POST, and text changed away and back to its submitted value. Actual deferred API responses must drive the committed note/detail cache and visible result. Root establishes RED before production edits.

Then implement revision-aware settlement and verify unchanged/changed draft success and failure, captured whitespace-trimmed submission, subsequent submission of the retained draft, real day GET/mutation completion ordering and ordinary errors, real A-to-B-to-A routing, and actual Root expiry/logout/relogin isolation. Reuse existing cancellation behavior; no extra provider/day invalidation. Run focused existing Student edit/notes/history/calendar/deletion and auth compatibility tests, types and lint. Root runs broad checks only after changes settle.

A fresh independent task review and final complete branch review must assess SPEC and QUALITY against this behavior and actual source; prior source CI does not accept the new change. Root integrates/pushes only after those gates, then records exact combined CI and separate runtime acceptance.

## Current evidence and remaining scope

Baseline parent is `517f5ea`; source runtime candidate `f423afc` has seven passing CI jobs and a successful immutable build. Its staging deployment queue expired before execution; another session changed staging to `00009-bcw`, requiring ownership/state reconciliation and new guard review. This note task does not establish a deployment or change that service.

Implementation and independent task/full-branch review are complete. Root established RED (one control passed, two edited drafts failed), then GREEN (95 tests across nine files), TypeScript and focused lint. The fix was integrated as `6567a9e` from isolated `42c01dc`. Combined with reviewed PR67/68 at `68f2fa2`, 102 tests across ten files passed in 9.76s, with TypeScript, focused lint and diff checks passing. Publication and exact combined CI are complete at `1f783001` / CI37040671313 (all seven jobs successful); separate runtime acceptance remains pending. Later Reports/PR69/70 source `11249217` also passed exact CI37043235047 (all seven jobs); its protected build queue expired75 before helper execution, preserving no new image/runtime claim. Existing full grading policies/terms/enrollment, independent Insight and generated draft provenance, real provider/email acceptance, native production adoption/drain/rollback/domain cutover, and dedicated runtime IAM acceptance remain separate backlog.
