# Super Teacher documentation

Index of the documents in this directory. Start with the [repository README](../README.md) for a quickstart.

## Orientation

- [architecture.mdx](architecture.mdx) - architecture and data boundaries
- [teacher-workspace.mdx](teacher-workspace.mdx) - teacher flows, frontend and authentication
- [agent-architecture.md](agent-architecture.md) - source entry points and test routing for coding agents
- [adr/](adr/README.md) - architecture decision records
- [ROADMAP.md](ROADMAP.md) - roadmap and ideas

## Development and testing

- [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) - managed demo launcher and manual setup
- [E2E.md](E2E.md) - browser regression tests
- [AI_EVALUATION.md](AI_EVALUATION.md) - offline AI grounding evaluation
- [PERFORMANCE.md](PERFORMANCE.md) - read-side performance
- [ACCOUNT_ADMIN.md](ACCOUNT_ADMIN.md) - local account administration

## Product behaviour

- [SCHOOL_CALENDAR.md](SCHOOL_CALENDAR.md) - school calendar
- [TRANSFERS.md](TRANSFERS.md) - section transfers and grade history
- [LOGIN_RATE_LIMIT.md](LOGIN_RATE_LIMIT.md) - proxy identity for sign-in limits
- [plans/](plans) - accepted behaviour and implementation notes for individual features

## Deployment and operations

- [DEPLOYMENT.md](DEPLOYMENT.md) - configuration and deployment
- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) - deployment, rollback, recovery, credential rotation and incident triage
- [OPERATIONS.md](OPERATIONS.md) - source-level observability reference
- [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) - SQLite backup and recovery
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) - release verification checklist
- [CANDIDATE_VERIFICATION.md](CANDIDATE_VERIFICATION.md) - isolated candidate verification with `scripts/verify_candidate.py`
- [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) - deployment status and execution handoff; the current release ledger
- [releases/](releases) - dated release records

## Security

- [SECURITY_REVIEW.md](SECURITY_REVIEW.md) - security review, with [SECURITY_PATCHES.diff](SECURITY_PATCHES.diff)

## Plans, audits and point-in-time records

These record what was planned or true when written; check the current documents above before relying on them.

- [RELEASE_CHECKPOINT.md](RELEASE_CHECKPOINT.md) - historical release checkpoint (2026-10-02)
- [RELEASE_PLAN.md](RELEASE_PLAN.md) - deployment targets and cutover prerequisites
- [LEGACY_CUTOVER.md](LEGACY_CUTOVER.md) - legacy public-domain cutover prerequisites
- [LEGACY_IMPORT_PLAN.md](LEGACY_IMPORT_PLAN.md) - offline EduTrack roster import and historical archive plan
- [CLOUD_SQL_PLAN.md](CLOUD_SQL_PLAN.md) - durable PostgreSQL infrastructure proposal
- [IDENTITY_INTEGRATION.md](IDENTITY_INTEGRATION.md) - identity integration review and remaining work
- [SCALE_INTEGRATION.md](SCALE_INTEGRATION.md) - scale integration audit
- [OVERHAUL_AUDIT.md](OVERHAUL_AUDIT.md) - overhaul evidence and remaining work
