# Truthful risk status for insufficient evidence

Spec: original deep overhaul, docs/LEGACY_IMPORT_PLAN.md's no invented history
requirement, and verified live-source audit /tmp/st-next-backend-gap.md. The audit
is schema/synthetic evidence only, no private records. Execute after the offline
adapter implementation/review; root owns integration and expensive verification.

## Global constraints

- No migration, raw-record rewrites, real email/provider calls, or production data.
- Preserve existing numeric metrics, zero/null distinction, due-date/as-of rules,
  missing counts, owner boundaries and known-evidence risk thresholds.
- Unknown students are not flagged watch/at-risk, and never displace those concerns.
- Current source is authoritative; Graphify native coverage is missing.
- Worker owns scoped implementation/tests only. No child agents, builds, broad
  suites, dependency installs, browser/cloud execution, push or deployment.
- Root reviews, commits, pushes, and owns exact-commit hosted CI and recovery.

## Task 1: Unknown state across metrics, API, tools, AI and UI

Read /tmp/st-next-backend-gap.md for verified source anchors. Add risk `unknown`
when all risk aggregate evidence (average, attendance_rate, homework_rate, trend)
is None. It means insufficient usable evidence, not a new grading threshold.
Keep due ungraded test missing counts and catch-up advice while status is unknown;
due ungraded homework still has its existing factual completion metric. Numeric
zero is real evidence. Empty, notes-only, future-only and excused-only inputs are
unknown; present-only attendance and existing known-evidence golden cases retain
current behavior. Cached formerly on-track empty-record insights must miss cache
using updated fingerprints.

Adapt every affected REST/tool literal/filter/count/sort and TypeScript consumer.
Add explicit `unknown` student counts to Overview and ClassSummary, partitioning
all owned students consistently. Attention lists only include watch/at_risk;
unknown appears separately as missing evidence, with neutral “Not enough data”
label/styling and a roster filter. Fix unchecked sort dictionaries. API risk types
and AI tool schema/filter support all four states. Known-risk attention priority
is preserved. Frontend fixtures/interfaces must include the new count contract.

Dashboard/report copy must not say Everyone is on track or celebrate no flags
for an all-unknown or partly unknown roster. Identify records needing data;
known healthy rosters retain appropriate existing behavior. Deterministic AI
unknown insights explicitly lack evidence and recommend recording/reviewing work
or attendance, never a stretch task solely from absent evidence. Preserve any
known missing-work catch-up action. Tool/context status counts and wording must
be factual and distinguish unknown from an attention flag.

Meaningful focused tests cover pure/ORM/bounded-query agreement as-of, no-evidence
matrix, zero grades, current thresholds, due-null test/homework boundary, mixed
unknown/watch/at-risk overview/report success/counts/tenancy, risk filters and tool
counts, fallback advice/cache invalidation, and UI all-unknown/mixed/knownhealthy
copy plus neutral labels/filter. Include a synthetic adapter output handoff if
practical without real records. Run focused pytest/Vitest and lint/type checks;
root runs broad CI once settled. Own only directly affected source/test files;
coordinate any overlap with adapter tests (adapter owner keeps its own file).
Initially leave diff for review, no staging/commits/cloud calls.

## Task 2: Independent task and integration review

Review actual diff/report against Task1 and the audit/spec. Return separate
spec-compliance and quality verdicts with source locations and real risks. Do not
repeat passed tests, edit files, inspect private archive, or run broad/cloud work.
Root sends concrete fixes to implementer and requests scoped re-review.
