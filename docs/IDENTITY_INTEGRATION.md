# Identity integration review and remaining work

## Native migration integration update

During the authorized merge of `dae26a5`, native integrity revision `0002`
and all grade/enum CHECK constraints were retained. Accounts is now
`alembic/versions/0003_accounts.py`, revision `0003`, parent `0002`.
The ownership models preserve native constraints, the frozen `0001` adoption
check remains, and SQLite foreign-key settings are restored after migrations.
New regression cases cover `0001 → integrity 0002 → accounts 0003` with preserved
raw/history rows and constraints, plus startup/CLI rejection of the independent
accounts `0002`. Execution results belong to the root verification owner.

Read-only live metadata during this merge reported `superteacher-00006-cjv`,
100% traffic, image `superteacher:dae26a5`. Its environment names did not include
`AUTH_MODE`, but that source runs accounts migrations even in passcode mode.
The serving replica may therefore already carry the independently published
accounts `0002`. No database or secret payload was retrieved to determine its
actual schema. Startup and Alembic CLI now reject ambiguous `0002` histories
before DDL instead of interpreting them as native integrity or silently stamping.

Before promoting the integrated image against that replica, restore a private
consistent copy, inspect its version/schema and validate an explicit adoption
mapping that preserves owners, sessions, quotas and domain/history records.
Retain the original snapshot and verify constraints on the adopted copy.
This adoption path remains a deployment blocker; changing the version number
alone does not apply native integrity checks or establish schema compatibility.

## Current integration and verification

The native merge now ports email login, token verification, the account menu and
export/delete flows into TypeScript. Session generations and private query-cache
replacement remain. Owner filters cover native assessment/note edits, calendar,
transfers, grade history, bounded summaries, reports and AI tools/cache. Transfers
retain raw grades; exports include historical assessment metadata. Strict origins
and trusted-proxy cookie handling remain. Parent drafts exclude confidential notes.

Signup/starter creation and quotas use database transactions. The configured owner
can adopt at the full signup cap. WebSockets revalidate sessions before turns and
during generation; watcher polls do not extend idle expiry. Shielded task cleanup fixes repeated ASGI cancellation; four focused auth,
revocation and calendar cases passed.

Focused evidence: 10 frontend accounts tests; 29 concurrency/lifecycle/export/mailer
cases; two idle-session cases; 11 selected tenancy/storage/migration cases;
13 selected auth/token cases; and 10 native AI/calendar/chat cases passed.
These separate runs do not establish full combined release readiness. Exact-commit
CI, PostgreSQL and browser lifecycle gates remain required. No real mail was sent
and no integrated image has been deployed.

The earlier findings below are historical, not current unresolved defects.
Existing accounts-0002 adoption, release checks and production email remain open.

Read-only review updated 2026-10-02 at 05:05 UTC (2026-10-01 Pacific).
The native checkout is `/home/jkail/projects/superteacher`, reviewed at
`034428412cefcc0aaee2a03d6386e1a1d1c30835`. Accounts candidate
[PR #12](https://github.com/jckail/superteacher/pull/12), `team/accounts`, was
fetched into `refs/remotes/origin/accounts-review` and inspected at exact commit
[`c2d8edddf3aa0ec3758fa76cde2d993a66329505`](https://github.com/jckail/superteacher/commit/c2d8edddf3aa0ec3758fa76cde2d993a66329505).
The earlier `de52835` snapshot and missing-browser-flow finding are superseded.
No foreign worktree was checked out or edited; no candidate tests, builds,
dependency installs, browser checks, real mail or paid AI calls were run.

## Historical candidate review (before native integration)

The product contract is **passwordless email sign-in**. First successful token
verification creates an account and a synthetic starter classroom; recovery is
requesting another sign-in link. There are no passwords or password-reset screens.
`web/src/auth.jsx` selects accounts/passcode mode through `/auth/config`;
`EmailLogin.jsx` requests a link, and `VerifyEmail.jsx` reads `/auth/verify#token=…`,
removes the fragment from history and POSTs the token. Account export/delete,
logout-all, demo notice and quota messages also exist. Port these behaviors into
the native TypeScript frontend and preserve its accessibility and editing tests.

Server tokens and sessions store hashes; token consumption uses a conditional
UPDATE, and verification rotates the previous session. Request-link replies are
generic for blocked, capped and unknown addresses. GET link scanning does not
consume tokens. The file mailer now names messages using time plus randomness;
SendGrid disables tracking and avoids logging recipient/token contents.
These source observations do not establish production delivery or integration.

## Historical findings at the reviewed commit

1. **Migration revision collision and storage regression.** Native
   `alembic/versions/0002_data_integrity.py` and candidate
   `alembic/versions/0002_accounts.py` both declare `revision = "0002"`, parent
   `0001`, with different meanings. Keep native integrity `0002`; add accounts as
   a distinct successor and retain its numeric/enum CHECK constraints in models
   and migrations. Establish whether any candidate accounts `0002` databases
   exist before designing an adoption path. Native `db._validate_legacy_baseline`
   refuses unsupported schema drift; candidate `db.run_migrations` instead stamps
   any database with a model table. Preserve the frozen-baseline validation and
   SQLite foreign-key restoration/checks; add PostgreSQL migration coverage.
2. **Transfers delete grades and summaries include historical grades.** Candidate
   `routers/roster.sync_scores` deletes other-section score rows. Native retains
   them and exposes `/students/{id}/grade-history`. Candidate `queries.load_summaries`
   reads all student scores and attendance, while native bounded summaries restrict
   scores to the active section and attendance to the school date. Add ownership
   to native behavior; preserve raw points, prior-section metadata, bounded history
   reads and history UI/export. Never replace the native transfer implementation.
3. **Native calendar, editing and numeric contracts are absent.** Candidate metrics
   use `date.today()` and lack `as_of`; its tree lacks the school-calendar module,
   assessment PATCH, note PATCH/DELETE and grade-history route. It restores the
   1.5-times-maximum score cap and two-decimal CSV rendering. Integrate ownership
   into the native routes, atomic numeric validation, school timezone and request
   snapshot, full-precision CSV and browser edits. Keep native course-plus-initial-
   section atomic creation. Candidate frontend JS files are older implementations,
   not replacements for the native TypeScript pages.
4. **Connected WebSockets do not revalidate revoked sessions.** Candidate
   `routers/ai.chat_ws` resolves `CurrentUser` once at the handshake and captures
   it for all later turns. Expiry, logout-all, disable and account deletion therefore
   need checks on the original connection before each authorized turn. Define and
   test cancellation of ongoing generation. Retain native bounded context/tools,
   disconnect cleanup, request timeout and shared capacity across chat/insights/
   drafts; candidate uses a chat-only semaphore instead.
5. **Strict origin and proxy trust behavior regresses.** Candidate
   `auth.AuthState.origin_ok` accepts the same host with either HTTP or HTTPS;
   native compares normalized scheme/host/port. Candidate `_secure` trusts raw
   `X-Forwarded-Proto`; retain native trusted-proxy origin/IP/cookie tests and policy.
6. **Parent-draft privacy regresses.** Candidate `reports._context` sends teacher
   notes and puts instructions/data together in a user message. Native excludes
   confidential notes, separates system instructions from escaped student data,
   and distinguishes not-yet-due work. Preserve native privacy, capacity, deadlines
   and client cleanup while adding the candidate quota hook and observability.
7. **Owner adoption can be blocked by the full user cap.** Migration creates
   `owner0000000` with a placeholder email. `accounts.get_or_create_user` supports
   adopting it via `accounts_owner_email`, but `auth.request_link` suppresses mail
   when that email is not already present and the user cap is full. Permit the
   configured bootstrap case and use `normalize_email` for both configured and
   incoming addresses; the configured address currently only strips/lowers.
8. **Signup and quota concurrency need a deployment decision.**
   `get_or_create_user` checks cap then inserts/commits without an atomic cap
   claim or same-email conflict recovery, then seeds separately. Concurrent
   same-email verification can hit the unique email constraint; failed seeding
   can leave an account without its starter classroom. `consume_quota` uses a
   process-local lock and read/modify/write counters, so multi-process correctness
   is not established. Make these paths transactional/atomic for the intended
   topology, or explicitly constrain the supported topology and test it.

## Historical ownership integration plan

Candidate `queries.py` contains `owned_course`, `owned_section`,
`owned_assessment`, `owned_student` and owner-scoped roster reads. REST routers,
reports, chat snapshots and tools generally thread `user.id`; insights authorize
before student-keyed cache access. Adapt these mechanisms into native services.

Inventory every native route and query/tool entry point, including
`student_candidates`, `iter_summaries`, `summaries_for`, `load_grade_history`,
assessment edits, note edits/deletes, calendar/overview, backup/admin paths and
new account lifecycle routes. Decide which system operations require operator
access rather than ordinary account access. Scope foreign filter IDs and payload
IDs; authorize both student and destination before transfers; authorize notes
through their student. Authorize before cache hits or quota charges. Preserve
uniform 404 behavior for foreign resource IDs and unchanged raw rows on denial.

Account export must retain historical assessment metadata as well as score IDs.
Account deletion must remove owned active/history data and invalidate connected
sessions. Preserve native deployment/persistence/backup files during integration;
none of the older candidate manifests supersede the current Cloud Run contracts.

## CI evidence

At 05:05:20 UTC, current commit `c2d8edd` had **lint, API, web, E2E and Docker
success** in
[run 36967089684](https://github.com/jckail/superteacher/actions/runs/36967089684).
Do not treat candidate CI as proof of compatibility with native main: it tests
its older branch contracts. Refresh the exact head and completed checks before
approving integration.

Historical commit `de52835b154bce4a2bec2d9bec73c5a508d05542` failed
[run 36966515994](https://github.com/jckail/superteacher/actions/runs/36966515994):

- E2E: 81 passed, 1 failed. The accounts lifecycle scenario
  `e2e/accounts/accounts.spec.ts:44` timed out at line 101 waiting for visible
  `getByRole('navigation', { name: 'Main' })` after signing in again. The failed
  assertion establishes the second-sign-in step; it does not alone establish
  the product root cause.
- Docker: image smoke test could not reach port 8080 during its health polling
  (connection reset, then refused connections). The failed-step log does not
  contain the container traceback, so it does not prove the startup cause.
- `c2d8edd` adds runtime `httpx` and time-ordered file-mailer names, with
  `tests/test_runtime_requirements.py`. Its successful Docker and E2E reruns supersede
  those historical failures. They do not clear the native integration blockers.

## Required checks after integration settles

- Migration matrix: empty DB, supported unversioned legacy DB, native `0001`,
  native integrity `0002`, and any actually existing accounts `0002` DB. Compare
  raw IDs/points/notes/attendance/cache/history and constraints; check SQLite
  foreign keys/pragma restoration and PostgreSQL behavior.
- Two-owner matrix: all native additions, foreign IDs/filters, atomic batches,
  reports/export/delete, chat context/tools/cache and operator-only endpoints.
- Owner adoption at full cap, signup/starter isolation, concurrent same-email
  signup/cap/quotas with independent sessions and intended worker topology.
- Token expiry/replay/tampering/scanner GET, generic link replies, fragment
  removal, mail privacy/failure, trusted proxy origin/IP and cookie/expiry rules.
- Logout/logout-all/disable/delete while the original chat remains connected;
  subsequent turns and ongoing-work cancellation policy.
- Native transfer/history/calendar/numeric/edit regressions and browser email
  signup, expired-link recovery, export/delete and privacy clearing. Production
  delivery/configuration verification uses the agreed provider and no real mail
  during automated tests.

Graphify's shared corpus lacks native Superteacher code coverage; exact Git
objects and live native sources were inspected directly. This document contains
curated project facts only; no private material was uploaded to hosted memory.
