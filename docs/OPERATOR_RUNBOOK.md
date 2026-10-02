# Operator runbook

Start here for deployment, rollback, recovery, secret rotation and incident triage.
This guide consolidates the procedures for the single-writer SQLite/Litestream
pilot. The release coordinator owns cloud execution and acceptance; a procedure
or passing source CI does not establish that a release is serving.

## Establish the target and evidence

Record the explicit project, region, service, serving revision, image digest,
source commit, replica URI, authentication mode and runtime identity privately.
Check the custom-domain target separately: a release to the native service does
not move a domain mapped to the legacy service. Recheck live metadata before any
change; dates, revision names and task completion in a document are observations.

| Need | Record or source to consult |
| --- | --- |
| Release owner's artifact, staging and recovery evidence | [Deployment ledger](DEPLOYMENT_STATUS.md) |
| Other session's production lineage, email and owner decisions | [Release checkpoint](RELEASE_CHECKPOINT.md) |
| Exact-source checks and remaining acceptance gates | [Release checklist](RELEASE_CHECKLIST.md) |
| Scoped account disable/sign-out and private audit outcomes | [Local account administration](ACCOUNT_ADMIN.md), [CLI source](../superteacher/admin.py) |
| Historical design proposals and current navigation | [ADR index](adr/README.md) |
| Settings and helper interface | [Deployment reference](DEPLOYMENT.md), [deploy helper](../scripts/deploy_cloud_run.sh) |
| Legacy preservation and domain prerequisites | [Legacy cutover](LEGACY_CUTOVER.md), [domain ADR](adr/0005-domain-cutover.md) |

The ledgers contain dated evidence and superseded attempts. Older plans and ADR
proposals are historical context, not an alternative deployment procedure. In
particular, older examples of `--to-latest`, canary splits, immediate rollback,
accounts migration `0002`, or health failures returning HTTP 200 must not override
the current source rules below. Archival cleanup is still tracked in
[GitHub #41](https://github.com/jckail/superteacher/issues/41).

## Deploy and accept a release

1. Select the reviewed source commit and its successful CI run. Have one
   verification owner inspect active jobs across worktrees before installs,
   builds or broad suites. In WSL, use `agent-heavy-check` in the foreground.
   Preserve logs on lock exit 75 or timeout; do not retry an unchanged blocked
   action or bypass the gate.
2. Have the release owner select the operator bundle and verify its source,
   archive hash, image digest and proof bindings. Prepared helpers are not
   executed evidence. Private candidate helpers can be bound to older commits;
   do not reuse them for a new source without review. The repository helper
   builds a tag and stages a revision; it does not provide the private bundle's
   exact-artifact/recovery proof and it includes `--allow-unauthenticated`.
3. Before isolated staging, verify a fresh, nonshared replica prefix with no
   writer, including other revisions of the staging service. The repository
   helper requires explicit `PROJECT`, `SERVICE`, `REPLICA_PREFIX` and runtime
   identity. Its drain exception is limited to `superteacher-overhaul-staging`,
   an `overhaul-staging/...` prefix and `ISOLATED_CANDIDATE_CONFIRMED=yes`.
   These inputs record an operator assertion; they do not discover writers.
4. For shared storage, preserve a consistent snapshot, rehearse migration and
   recovery on a copy, stop new writes, close active WebSockets, and observe the
   old writer stop and final replica sync. `--no-traffic`, disabled deploy health
   checks and maximum one instance do not prevent invocation from starting a
   second writer. Do not invoke a shared-prefix candidate before this drain.
5. Run the selected isolated candidate's health/version, protected-route,
   authenticated workflow, synthetic write, recovery and receipt-readback
   checks. [Candidate verification](CANDIDATE_VERIFICATION.md) describes the
   [verifier](../scripts/verify_candidate.py); its normal mode writes synthetic
   records and requires isolated storage. Retain private credentials/receipts.
6. Recheck the serving revision and drain before promotion. The repository
   helper's `--promote NAMED_CANDIDATE_REVISION` requires
   `DRAINED_WRITER_CONFIRMED=yes` and `DRAINED_WRITER_REVISION` naming the recorded
   drained revision at 100% traffic, plus exactly one literal candidate replica URL matching
   the supplied bucket/prefix. It does not verify drain itself. Verify the actual
   serving version, authentication, workflows and persistence after promotion.
   Email accounts and custom-domain cutover have their own acceptance gates.

## Roll back or recover

**Choose using database compatibility, not just image age.** First stop new
writes and drain the candidate writer. Verify the actual database lineage
against the proposed rollback image; startup may migrate it and an older image
may not support the resulting schema. Record what happens to writes since cutover.
There is no automatic rollback in the repository deploy helper.

If the image and current database are compatible, the release owner can select
the known compatible revision explicitly after the writer handoff. If they are
not, restore into a separate database and recovery replica prefix, rehearse the
intended release, and perform a new verified handoff. Preserve the original
database, sidecars and replica; a traffic shift alone is not a data rollback.

Use [SQLite backup/recovery](BACKUP_RECOVERY.md) for a filesystem snapshot. The
`python -m superteacher.backup SOURCE DESTINATION` command opens its source
read-only, copies through SQLite's online backup API, checks integrity/foreign
keys and refuses an existing destination. Copying only a live `.db` file can
miss WAL contents. Rehearse in a new file with the intended release, its own
configuration and `SEED_DEMO_DATA=false`; application startup can migrate it.

For a Cloud Storage replica, the release owner restores with the pinned
Litestream tool into a new private file, without launching a server or replica
writer on the source prefix. Verify integrity, foreign keys, migration lineage
and expected reference records. See [deployment recovery evidence](DEPLOYMENT_STATUS.md)
and [identity adoption](IDENTITY_INTEGRATION.md) for the native integrity `0002`
and accounts `0003` chain. An independently published accounts-`0002` database is
ambiguous to native startup: use the reviewed offline adoption path on a copy,
not an Alembic stamp or a reused migration ID.

## Rotate credentials and sessions

Inventory secret *references and versions*, never their values. The release
owner prepares a new credential/version, verifies runtime access, selects the
explicit version for a reviewed rollout, verifies the consumer, then retires
the old credential after the rollback window. A credential rollout follows the
same writer-drain rules as a code rollout.

| Credential or action | Verify before declaring success |
| --- | --- |
| `AUTH_PASSWORD` / `SESSION_SECRET` | New passcode login works; old signed passcode cookies are rejected. Rotating `SESSION_SECRET` alone does **not** revoke accounts-mode database sessions. |
| Account session revocation | The authenticated user's `POST /api/auth/logout-all` revokes that user's sessions. Whole-service revocation is separate operator work; there is no global admin endpoint here. |
| Mail credential | Check the selected SendGrid/SMTP backend and sender, then actual inbox delivery and link consumption. Provider acceptance and generic HTTP 202 are not delivery proof. |
| `ANTHROPIC_API_KEY` / `METRICS_TOKEN` | Verify the selected consumer with synthetic data or the protected metrics endpoint; keep tokens and generated content out of handoffs. |

See [email/settings reference](DEPLOYMENT.md) and current
[authentication](../superteacher/auth.py), [sessions](../superteacher/accounts.py)
and [mailer](../superteacher/mailer.py) source. Accounts, passcode and credential
changes can have different revocation effects; test the intended mode.

## Scoped account administration

For a single accounts-mode user, the reviewed [local CLI](ACCOUNT_ADMIN.md) supplies
`disable`, `enable`, `sign-out` and usage inspection. The release owner must identify
the actual database and access window; modifying an arbitrary restored copy does
not revoke the serving writer's sessions. The CLI requires an existing database
at this checkout's native migration head and does not migrate it, create a new
one or authenticate an operator. Follow its full procedure before invoking it.

`disable` revokes that account's sessions and unconsumed login links while preserving
classroom data and quota evidence. `sign-out` revokes sessions/links without disabling;
new link requests remain possible. `enable` does not restore revoked sessions or
links. None cancels work already in flight. The implicit passcode owner is refused;
use the passcode/session rotation procedure above for that mode. Account deletion,
export and quota reset are separate capabilities, not CLI incident workarounds.

Mutation commands require an asserted operator ID and a private operator-owned
`0600` JSONL audit file. Keep the mapping of operator IDs and account-list output
(which includes emails) private. Audit records contain IDs and outcome counts,
not emails, tokens or student contents. Exit `3` means the database committed but
the audit outcome could not be persisted: reconcile actual account/session state
and the intent event before retrying. A crash can likewise leave an unmatched
intent. Do not erase the audit log to make a retry pass. The CLI is a local
filesystem tool, not a global admin endpoint or proof of production acceptance.

## Incident checklist

1. Record the affected service/revision, time and request ID; identify the
   release owner. Preserve private diagnostics and the last accepted artifact.
2. Distinguish process/database health from readiness. Current
   [`/api/health`](../superteacher/main.py) returns HTTP 503 for database failure;
   [`/api/ready`](../superteacher/observability.py) also requires the database's
   migration revision to match the code head. Healthy is not sufficient to accept
   a release. Use [log/metrics reference](OPERATIONS.md) to correlate failures;
   its older Cloud Run traffic examples are not single-writer rollout guidance.
3. For `litestream_restore_failed`, preserve the fail-closed behavior. Check
   replica URI, runtime access and copied-file readability before changing
   ports/timeouts. A nonexistent prefix can appear to be first boot, so verify
   the intended replica rather than accepting an empty database as recovery.
4. For sign-in mail failure, inspect sanitized provider diagnostics and
   `/api/auth/config`. The breaker opens after three consecutive failures and
   permits a recovery probe after its cooldown. `email_available` describes
   process-local breaker health, not successful inbox delivery. Coordinate a
   verified mail recovery or reviewed mode rollback with the release owner;
   disabling authentication is not a recovery step.
5. For schema/replica uncertainty, hold promotion and use the recovery procedure
   above. Preserve serving revisions and custom-domain routing until the
   selected replacement and rollback path are verified.
6. Record the exact source/image/revision, executed checks, data-loss boundary,
   remaining blockers and next owner in the existing release ledger. Keep
   credentials, transcripts, backups and student contents outside Git and hosted
   task notes. Alert-policy implementation remains tracked in #24; examples in
   the metrics reference do not prove monitoring is deployed.
