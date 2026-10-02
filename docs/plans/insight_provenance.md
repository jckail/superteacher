# Insight calculation provenance and explicit refresh

Bounded prerequisite for JCK-70 / GitHub #38; this does not implement intervention
plans or claim the issue complete. Keep existing initial Insight GET, cache,
provider retries, quotas, owner checks and mutation invalidations unchanged.

Return required `as_of` from the exact metrics object used for fingerprint and
prompt on new AI, owned cache hits and rule fallbacks. This is a calculation date
cutoff, not a snapshot or proof that same-day records remain unchanged. Retain the
cache's actual `generated_at`; rules have no AI generation timestamp. No migration.

Show independent Insight cutoff and AI generation time. Older retained client
payloads without the additive field show an unknown cutoff, never the Student
metrics date or browser date. Reuse the shared school-calendar query only to
identify an older cutoff; calendar updates must not refetch Insight. Calendar
failure must not claim current freshness. Always explain the same-day limitation.

Offer one explicit Refresh insight action, disabled during fetching and guarded
synchronously against duplicate calls. It may consume AI allowance on a cache
miss and does not force generation on a cache hit. Preserve old content and its
provenance on error; the same action replaces the existing error retry control.
No new automatic day/Attendance/provider request policy, draft changes or edits
to other Student behaviors.

Focused acceptance: actual QueryClient/component and full Student day advance,
no extra Insight request, AI timestamp/cutoff separation, rules/unknown cutoff,
deferred duplicate refresh, error retention/retry, student key changes and aborted
old reads. Backend synthetic fake-provider tests cover all response paths, cache
hit timestamp/no quota charge, cutoff held across generation, day miss and rules.
Native pytest requires CI if local SQLAlchemy is unavailable. No real providers.

## Author checkpoint

Implemented in isolated `fix/insight-provenance-20261002` from `7ca238a`.
Focused frontend RED: six feature assertions failed on the original card (only
exporting its existing component as a test seam). GREEN: eight focused tests pass,
including actual full Student shared-calendar coalescing and actual Root logout /
same-ID new-session isolation during deferred old and new Insight refreshes.
TypeScript and focused ESLint pass; Python Ruff, AST and diff checks pass.
Native backend tests are authored but unexecuted locally because SQLAlchemy is
unavailable; root's exact-head CI must qualify them. No install or real provider.
Existing transport retry policy remains unchanged: one deliberate refetch action
is not a promise of exactly one network attempt after a transport failure.
The temporary existing-dependency symlink was removed before source handoff.
