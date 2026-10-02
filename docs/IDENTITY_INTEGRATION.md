# Identity candidate integration review

Read-only source review on 2026-10-01. The authoritative checkout is
`/home/jkail/projects/superteacher`; the independently active candidate is
`/home/jkail/work/st-accounts`. Candidate files may change concurrently. This
document records observed implementation and required checks, not candidate
completion or passing tests. No candidate edits, merges, tests, builds, installs,
or browser checks were performed. The root agent owns verification.

## Blocking differences

1. **Migration identity collides.** Native
   `alembic/versions/0002_data_integrity.py:11` and candidate
   `alembic/versions/0002_accounts.py:19` both declare revision `0002`, parent
   `0001`, but apply different schemas. Copying both files produces duplicate
   revision identities. Replacing one with the other leaves an already stamped
   `0002` database without the replacement's schema changes. Keep the native
   integrity revision and introduce a distinct accounts successor for native
   databases. If candidate databases have already been migrated, their `0002`
   has a different meaning and needs an explicit adoption path; first establish
   whether such databases exist.
2. **Candidate transfer code deletes grade history.** Candidate
   `superteacher/routers/roster.py:45` deletes scores from other sections during
   `sync_scores`. Native transfer code retains them and exposes
   `/students/{id}/grade-history`. Integrate ownership into native transfer
   behavior instead of replacing it with candidate code. Candidate summary
   loading (`superteacher/queries.py:66`) also includes every score belonging to
   selected students; native summaries exclude historical sections. Preserve
   that active-section restriction.
3. **Candidate browser authentication is incomplete.** Candidate
   `web/src/pages/Login.jsx:1` submits only a passcode, and `web/src/auth.jsx:1`
   has no accounts mode selection or link verification. No `request-link`,
   `verify`, or `auth_mode` handler appeared in the inspected candidate browser
   source. Account mode rejects `/auth/login`; emailed `/auth/verify#token=...`
   therefore needs an implemented browser flow before switching modes.
4. **Existing WebSockets outlive revoked sessions.** Candidate
   `superteacher/routers/ai.py:88` resolves `CurrentUser` at connection setup,
   then uses that captured identity for later turns without another session
   check. `accounts.resolve_session:247` enforces expiry/disabled status and
   `revoke_all_sessions:275` removes sessions, but those changes are not checked
   by an already connected chat. Revalidate before each authorized turn and
   define cancellation behavior for ongoing generation. Existing candidate
   session tests check reconnection after logout, not continued use of the
   original connection.

## Ownership integration

Candidate `queries.py:24-39` has owner-scoped course, section, assessment and
student lookup helpers. Candidate REST routers receive `CurrentUser`, report
loads pass `user.id`, chat context passes the owner, and `ai_tools.execute:266`
requires an owner. `ai.ai_insight:353` expects a previously authorized student
before accessing its student-keyed cache. These mechanisms should be adapted
into the native bounded query/context/capacity implementation.

Native assessment PATCH, note PATCH/DELETE, grade-history, `student_candidates`,
`iter_summaries`, and school-calendar paths postdate the inspected candidate.
Audit every native route and every query/tool entry point, including foreign
filter IDs and write payload IDs. Authorize both the student and destination
section before transfers; authorize notes through their owning student. History
and account exports must retain all owned historical assessment metadata, not
only score IDs. Keep owner authorization ahead of cache hits and quota charges.

Native `auth.py:132` compares normalized scheme/host/port. Candidate
`auth.py:130` accepts the same host with either HTTP or HTTPS. Preserve the
native same-origin behavior and its trusted-proxy tests during integration.

## Bootstrap, links and recovery

Candidate migration backfills existing courses to deterministic
`owner0000000`; `accounts.get_or_create_user:151` adopts that user's existing
data for configured `accounts_owner_email`. New users receive starter data.
`auth.request_link:302` gates delivery by user cap before owner adoption:
when the cap is full, the still-placeholder owner's configured address is not
an existing email and receives no link. Allow and verify that bootstrap case.
Use the same email normalization for the configured owner and input addresses.

The observed design is passwordless: signup happens only after email-token
verification, and requesting another link provides recovery. There is no
password-reset implementation. Confirm that this meets the intended product
contract before presenting password/signup/reset screens.

`accounts.consume_login_token:205` atomically marks a live token consumed;
tokens and sessions store hashes. Link replies are generic, delivery runs after
the response, fragments keep tokens out of URL queries, and `mailer.py:71-125`
redacts recipient/token/error contents and disables tracking. Provider delivery
and usable production link configuration still need verification. Do not send
real mail during tests.

`get_or_create_user` checks the user cap and inserts without a shared creation
lock or atomic cap claim. Same-email concurrent verification can reach the
unique email insert without an `IntegrityError` handler. Quota increments
(`accounts.py:329`) use a process-local lock and database read/modify/write;
cross-process quota correctness is not established. Verify these concurrency
paths against the intended deployment topology.

## Required candidate checks after integration settles

- Migration matrix: empty database, supported unversioned legacy database,
  native `0001`, native integrity `0002`, and any actually deployed candidate
  accounts `0002`. Compare raw IDs/points/notes/attendance/cache/history before
  and after; preserve constraints and validate foreign keys. Retain native
  `db.py:94` frozen-baseline drift refusal rather than candidate's broad
  stamp-if-any-table logic (`db.py:79`). Check SQLite batch migration pragma
  restoration and PostgreSQL schema behavior.
- Two-owner route matrix covering all native additions, foreign IDs/filters,
  batch writes, reports, exports/deletion, chat context/tools and cache hits;
  verify denied writes leave raw rows unchanged.
- Legacy owner adoption, full cap bootstrap, new signup and starter isolation;
  concurrent same-email signup/cap/quotas using independent DB sessions.
- Token expiry/replay/tampering/scanner GET, generic blocked/unknown replies,
  fragment removal from browser history, mail privacy and delivery failure,
  trusted proxy origin/IP, cookie flags/rotation/idle and absolute expiry.
- Logout, logout-all, disable and delete while chat is already connected;
  reject subsequent turns and verify ongoing-work cancellation policy.
- Native transfer/history/metrics and numeric CSV/edit regressions, plus
  browser email sign-in, link verification, expired-link recovery and account
  export/delete. Reconcile candidate tests with native fixtures instead of
  replacing native regression coverage.

Graphify's shared corpus lacks native Superteacher code coverage; source was
inspected directly. Agent Hub did not identify the candidate checkout. No
private material was uploaded to hosted memory.
