# Architecture decision records

These five records preserve proposals written on 2026-10-02 against `origin/main`
(`bb23101`) and a read-only inspection at that time. They are historical design
context, not current deployment instructions or proof of owner approval. Their
cost estimates, timing estimates, migration assumptions and observed service
state must be rechecked before acting.

## Current operational entry points

Start with the [operator runbook](../OPERATOR_RUNBOOK.md), then the release owner's
[deployment ledger](../DEPLOYMENT_STATUS.md) and [release checklist](../RELEASE_CHECKLIST.md).
Current source includes single-writer SQLite/Litestream persistence and email-link
accounts; that implementation does not establish the serving revision, successful
recovery, owner-account adoption, email delivery or a domain cutover. The release
owner qualifies those gates separately. [Legacy preservation](../LEGACY_CUTOVER.md)
is required before changing the legacy service; synthetic-looking data does not
establish that there is nothing to migrate.

Use [local account administration](../ACCOUNT_ADMIN.md) for the reviewed filesystem
CLI, and [the roadmap](../ROADMAP.md) for remaining product work. Proposed Google
sign-in, pseudonymisation/ZDR arrangements and configurable grading below remain
proposals unless their own current records establish otherwise.

## Historical proposal index

| # | Record | Status | One-line recommendation (monthly cost at 1 / 10 / 100 teachers, estimate) |
|---|---|---|---|
| [0001](0001-persistence.md) | Production persistence | Proposed, needs owner decision | Litestream to GCS with max-instances=1 for the pilot ($0-1 / $1 / $3), move to Cloud SQL `db-g1-small` (about $28) when you pass about 10 teachers or need multi-instance |
| [0002](0002-identity-and-tenancy.md) | Identity and tenancy | Proposed, needs owner decision | Google sign-in with an invite allowlist plus `courses.owner_id` ($0 / $0 / $0); Clerk if you need organisations soon |
| [0003](0003-privacy-and-ai-data.md) | Student privacy and AI data | Proposed, needs owner decision | Pseudonymise prompts, notes off by default, request Anthropic ZDR and a DPA (about $0 infra; 3-5 days work) |
| [0004](0004-grading-policy.md) | Grading policy | Proposed, needs owner decision | Policy objects at section/course/owner level with defaults equal to today's numbers (about $0; 4-5 days for first slice) |
| [0005](0005-domain-cutover.md) | Domain cutover | Proposed, needs owner decision | Staging host `app.` first, then repoint `www` and apex mappings to `superteacher`; original empty-data assumption superseded—preserve legacy evidence (original estimate about $0) |

## Historical sequencing proposal

The original proposal sequenced durable persistence, per-teacher identity and
owner scoping, AI data minimisation/deletion/export, configurable grading, then
domain cutover. Its original service observations and one-engineer schedule are
superseded for operational use by the current records linked above. Preserve the
ADR reasoning while checking actual implemented behavior and unfinished gates;
do not use the old description of ephemeral SQLite or an empty legacy dataset as
a reason to rebuild storage or retire a service.

## Historical decision questions

These questions record the original options. Reconcile them with current owner decisions before requesting or recording a new decision.

| # | Question | Choices (recommended first) |
|---|---|---|
| 1 | Persistence | (a) Litestream/GCS now, Cloud SQL later; (b) Cloud SQL now; (e) Neon/Supabase; reject FUSE, Filestore, Firestore |
| 2 | Identity | Google sign-in + allowlist; Clerk; other. Also: invite-only pilot or school/org tier now? Which email owns the existing data? |
| 3 | Privacy | Approve pseudonymisation and notes-off default (yes/no); pursue Anthropic ZDR + DPA now (yes/no); engage counsel before any school (yes/no) |
| 4 | Grading | First slice = weights, scale, missing-work, attendance (yes/no); default for missing work in new courses: exclude or zero |
| 5 | Cutover | Staging host first then repoint (C then A); or swap revision of `edutrack` (B). Canonical host: www or apex. Where is DNS managed? Retire `edutrack` after 14 days (yes/no) |

## Historical owner questions

1. Who has access to the DNS provider for `the-super-teacher.com` (it is not in project `portfolio-383615`)?
2. Is the first audience only you, a few invited teachers, or a school?
3. Budget ceiling per month for the pilot?
4. Do you want to be told about the unauthenticated EduTrack API immediately and take the old site down now, ahead of the cutover?
