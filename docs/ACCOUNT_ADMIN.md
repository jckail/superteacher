# Local account administration

This CLI supplies the minimal operator surface in [#27](https://github.com/jckail/superteacher/issues/27).
It requires filesystem authority on the **existing, correct native SQLite database** and the repository's
Python environment. It does not authenticate an administrator, create a database, run migrations,
start the application, contact providers, or choose a deployment. Linux/WSL is supported; the audit
file uses POSIX ownership, permissions and locking. PostgreSQL is outside this tool's scope.

Coordinate the database path and access window with the release owner. Do not operate on an arbitrary
restored copy, another revision's disk, or a running replica and assume the changes reach the writer.
Follow [release acceptance](RELEASE_CHECKLIST.md) and [backup/recovery](BACKUP_RECOVERY.md) for
release/database ownership. Start with the consolidated [operator runbook](OPERATOR_RUNBOOK.md) for current ownership and recovery procedures.
The CLI never supplies missing credentials or authorizes a release.

## Inspect accounts and use

Activate the existing repository Python environment, then use an explicit file path:

```sh
python -m superteacher.admin --database /verified/path/superteacher.db list
python -m superteacher.admin --database /verified/path/superteacher.db usage ACCOUNT_ID
python -m superteacher.admin --database /verified/path/superteacher.db usage ACCOUNT_ID --day 2026-10-02
```

Replace the path and ID with verified values; these are examples, not deployment commands.
`list` prints account IDs, **email addresses**, disabled state and UTC timestamps. Keep stdout private;
do not paste it into public tickets or CI logs. The implicit shared-passcode owner is excluded.
`usage` prints the target account's used counts for `chat`, `insight` and `parent_update` on a UTC day
(today by default). Counts include failed model attempts when the service has charged them. This
command does not infer configured limits or remaining allowance: inspect the serving revision's
quota configuration separately. It does not change counters or the global budget.

The file must be at this checkout's exact native Alembic head and have the required account tables.
Older schemas, independently published accounts revision `0002`, missing files and incomplete
account schemas are refused. A revision marker alone is not a complete schema-integrity proof;
normal release integrity and lineage gates still apply. Reads open SQLite in read-only mode.

## Disable, enable and force sign-out

Prepare a protected audit directory under operator control. Mutations require `--actor` and `--audit`:

```sh
install -d -m 700 /private/operator-audit
python -m superteacher.admin --database /verified/path/superteacher.db disable ACCOUNT_ID \
  --actor OPERATOR_ID --audit /private/operator-audit/accounts.jsonl
python -m superteacher.admin --database /verified/path/superteacher.db enable ACCOUNT_ID \
  --actor OPERATOR_ID --audit /private/operator-audit/accounts.jsonl
python -m superteacher.admin --database /verified/path/superteacher.db sign-out ACCOUNT_ID \
  --actor OPERATOR_ID --audit /private/operator-audit/accounts.jsonl
```

`OPERATOR_ID` identifies the operator in your private access records; it is an **asserted ID**, not a
verified login or email address. IDs accept at most 64 ASCII letters/digits and `_ . : -`.
The file is created with mode `0600`. Existing files must have exactly that mode, be owned by the
invoking operator, have one hard link, and be regular files. Symlinks, database/sidecar paths,
incomplete final records and an audit lock held by another CLI are refused. Protect the directory
too; local access can otherwise replace or tamper with a log. This is not a tamper-evident service.

`disable` marks only the selected account disabled, deletes its sessions, and removes its outstanding
unconsumed login links. `sign-out` performs the same session/link revocation without disabling the
account. `enable` clears the disabled flag but does not restore sessions or links. An enabled account
must request a fresh login link. New links requested after a sign-out are not blocked. The implicit
passcode owner is refused: use the release owner's existing passcode/session rotation procedure.

The operation preserves the account, classroom records, per-user quota counters and global budget.
There is no delete, export, quota-reset or budget-bypass command. Revocation prevents subsequent
session resolution; it cannot cancel an API request or model call already in flight.

## Audit outcome and failure handling

Mutations reserve the SQLite writer, then persist an `intent` record before making changes. Each
JSONL record contains a UTC timestamp, random event ID, asserted actor ID, action and target account
ID. A `committed` outcome adds revoked session/link counts. Emails, token/session hashes, IPs and
student content are never included. A database failure rolls back the transaction and attempts to
record `rolled_back`. Read commands are not added to this mutation log.

The database transaction and filesystem log are separate durability domains. Exit `0` means the
database committed and its audit outcome was fsynced. Exit `2` means a refusal or failure: inspect
the fixed error and any intent/outcome before retrying. Exit `3` explicitly means **the database
committed but the audit outcome could not be persisted**; the message identifies the intent's event
ID. Reconcile the actual account/session state in a protected operator record before retrying.
A process crash after intent may also leave no outcome. An incomplete final line must be reconciled
before another invocation; do not erase the log to make a retry pass. SQLite lock waits are bounded
to five seconds; this tool does not retry a busy writer.

Securely retain/rotate the log according to the deployment's actual approved retention policy.
The CLI does not upload it or invent a retention period. Keep the private mapping of operator IDs
and incident records separate from account/student exports.

## Abuse procedure

1. Identify the serving writer and affected account IDs through protected operator access. Inspect
   usage for the relevant UTC day and distinguish charged attempts from completed AI responses.
2. Disable the affected account rather than deleting it to reset quotas. This preserves evidence,
   removes current sessions and pending links, and prevents that existing account from signing in.
3. For spam sign-ups, review the actual allowlist, total account cap, per-email/IP/global link limits
   and global AI budget with the release owner. Verify proxy identity before changing rate limits;
   do not weaken gates or increase quotas as an incident workaround.
4. Record the action using IDs and the audit event ID. Verify the disabled state and session removal.
   After resolving the incident, explicitly enable the account and require fresh sign-in.

Account self-deletion removes the account's usage counters. The current service does not retain a
retired-identity quota ledger, so delete-and-re-register can evade a per-account daily allowance.
This CLI does not solve that bypass. Avoid deleting an abusive account as containment; shared
global budget/sign-up controls limit exposure, subject to the serving configuration. Full auditing
of user-requested account deletion/export and durable re-registration abuse controls remain open
in #27. This local mutation audit must not be represented as coverage of those self-service routes.
