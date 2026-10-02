# Deployment status and execution handoff

Updated 2026-10-02. Deployment is authorized. Root owns release execution and
verification. The native overhaul is merged and isolated staging is deployed;
production service traffic and custom-domain mappings remain unchanged. Private
backup artifacts stay outside Git and hosted project memory.

## Current checkpoint and next action

Main source `5113de8` passed every gate in
[CI36978867068](https://github.com/jckail/superteacher/actions/runs/36978867068),
including **996 API tests and one known legacy-passcode logout xfail**. It adds
staging/drain and candidate replica-binding safeguards, with 25 focused mocked
deployment cases. Earlier source `9de97ce` passed all gates with 976 API tests and
adds exact pinned Litestream bookkeeping validation to the offline accounts
adoption helper. Neither change alters teacher-facing routes or frontend behavior.

The protected image build for this source stopped with exit75 at the shared
verification lock before any Cloud Build command/archive/image began. Log:
`/tmp/st-cloud-build-9de97ce.log`. Do not repeatedly queue the unchanged attempt
or bypass the lock. The deployed staging image below remains source `7166813`.
The corrected helper's private production-copy rehearsal now passed as described
below. A new serving image has not been built. A final post-drain snapshot,
compatible rollback and explicit live adoption/promotion procedure remain required.

The legacy API archive is preserved locally and in private versioned GCS with
verified SHA256 roundtrip; see [LEGACY_CUTOVER.md](LEGACY_CUTOVER.md). It is a
non-atomic API archive, not a consistent database backup. Preserve the existing
legacy data during the overhaul. Faithful import, dataset authority, compatible
rollback, final writer drain and domain cutover remain open.

## Verified native staging release

PR15 merged as `8ceb050` from tested source `7166813`. Exact source CI
[36970806343](https://github.com/jckail/superteacher/actions/runs/36970806343)
and merged-main CI
[36971521702](https://github.com/jckail/superteacher/actions/runs/36971521702)
passed every release gate. Source API evidence: **963 passed, one known xfail**.

Cloud Build `8e3a2ff4-19a1-421d-a0e8-c0de66687f29` succeeded. Image:
`gcr.io/portfolio-383615/superteacher@sha256:5d3c85dfb754bf5382ca7f196d86b108d878c2a85ccf2425702d22b0df7bcde6`.
Its exposed VERSION is the build ID, mapped to source `7166813`; it is not a Git SHA.

Isolated service `superteacher-overhaul-staging`, revision
`superteacher-overhaul-staging-00001-7kx`, is deployed at
https://superteacher-overhaul-staging-vbufkr2qma-uc.a.run.app.
It uses a separate replica prefix
`overhaul-staging/8e3a2ff4-19a1-421d-a0e8-c0de66687f29`, demo/AI disabled,
UTC calendar, passcode auth, max one instance and no minimum instances.
Health, readiness, actual login/calendar/version/SPA/logout passed. The reusable
candidate check passed synthetic course/initial-section/student/assessment/note/
attendance creation, exact raw 20.123456789/10, name edit, transfer/history,
active-section averages, rosters and authenticated logout. Private credentials and
receipts remain outside Git, mode0600; values are not included here.

Recovery-only job `superteacher-overhaul-recovery-8e3a2ff4`, execution
`superteacher-overhaul-recovery-8e3a2ff4-9jlsw`, restores the isolated prefix into a
fresh transient SQLite copy and checks the receipt. It overrides the entrypoint,
never starts the server or replication, and cannot write the serving database.
Execution succeeded at06:03:56 UTC. Its structured result confirms native0003,
integrity/FK success and preserved synthetic transfer history/records. The
candidate receipt readback also passed. This proves the staged replica can restore
the checked records; it does not prove a production restart or a zero-loss RPO.

A separate rehearsal job `superteacher-overhaul-adoption-8e3a2ff4`, execution
`superteacher-overhaul-adoption-8e3a2ff4-5wggt`, restores the existing service's
replica into a private transient copy and runs the adoption bridge there. It never
starts replication/server or writes the production prefix. The first execution correctly rejected restore-created SQLite sidecars. After
preparing a validated standalone backup, execution `vtgs9` reached exact-schema
validation and refused the copy because its schema differs from the frozen
published accounts0002 baseline. No output copy was published and no live schema
changed. The schema-only diagnostic execution `mnl7l` succeeded: all application/accounts
schema matched; only `_litestream_lock` and `_litestream_seq` were additional.
The bridge now reconstructs and validates the exact two-table DDL from pinned
Litestream0.5.17 in both independent expected schemas and preserves every internal
row. Missing pairs, extra columns/indexes/triggers and DDL drift remain rejected.
Twenty focused adoption tests passed, including real pinned local replication,
standalone backup and adoption. Exact-head CI subsequently passed (976 API
tests). A later bounded artifact rehearsal closes the production-copy
compatibility check without claiming a new serving image. A final cutover still
requires fresh post-drain adoption and verified serving-image configuration.

### Corrected helper against the real replica copy

Execution `superteacher-overhaul-adoption-8e3a2ff4-hbrzh` succeeded at
07:42:42 UTC. It overrides the existing immutable source7166813 recovery runtime's
entrypoint with a checked operator payload. The payload verifies the committed
source9de97ce helper SHA256
`f9247a09b83c7b6b611eae30635c9bfb1551478aee447937773d03f00cbf403e`
and six supporting source/migration hashes before any restore. Relative imports
use the actual image package; no dependency install or image build occurs.

The task restores the existing service replica into a private transient directory,
prepares a standalone read-only backup and adopts only a clone. Independent checks
confirm source0002/output0003, every non-version row preserved, unchanged source
snapshot bytes, integrity and foreign keys. The structured Cloud Logging result
was independently read and verified; a local mode0600 proof is retained at
`/tmp/st-9de-production-copy-proof.json`. Limits: one task, no retries, 180 seconds,
512Mi memory, 100-second restore deadline and 32Mi restored-file cap.

No server, replication writer, production schema change or promotion ran. The
source replica was read only; the existing runtime identity still has broader
IAM rights, so this is a code-mediated restriction, not an IAM-enforced read-only
principal. Transient clones were removed after verification. The existing service
can continue writing after this restore; final cutover needs its own fresh
post-drain snapshot. This targeted operator-artifact check does not validate a
new serving image or replace the shared build lock.

Public recheck after staging: www.the-super-teacher.com reports `v0.1.0`;
the existing direct superteacher service reports `dae26a5`, revision00006-cjv at
100% traffic. No production/domain/serving-prefix changes were made. Existing
accounts-0002 adoption, tested restored copy, single-writer drain and data-preserving
custom-domain cutover remain required. Request-based CPU may stall background
replication between requests; the pilot's documented RPO caveat remains.

## Latest release continuation

Later read-only metadata reported `superteacher-00006-cjv` at 100% traffic,
image `superteacher:dae26a5`. The observation table below is historical; its
`ce94d50` digest must not be used as evidence for the current release. Custom
domain mappings were still to legacy `edutrack` at the last verified inspection.
Reinspect all service/domain metadata before an authorized traffic change.

The native accounts merge preserves integrity `0002` and adds accounts `0003`.
The serving image may already have independently published accounts `0002`;
startup refuses that ambiguous history. Validate a consistent backup/clone with
an explicit schema adoption bridge before promoting against the existing prefix.
An isolated empty-prefix candidate can validate the new chain independently.

An earlier protected build attempt also stopped at the shared heavy lock; the
later source7166813 image and isolated deployment succeeded as recorded above.
The latest source9de97ce image attempt is blocked at that lock. Avoid overlapping
the independent persist deployment session or changing its processes.

## Historical targets (04:50 UTC)


Explicit project: `portfolio-383615`; region: `us-central1`. The gcloud active
credential is authenticated; its configuration has no default project. No local
ADC file was present; Terraform/library credentials need a separate probe before
using them. CLI authentication alone does not establish ADC or provisioner IAM.

| Target | Ready revision / traffic | Image / public result |
| --- | --- | --- |
| `superteacher` | `superteacher-00004-dgh`, 100% | `superteacher:ce94d50`; health 200, version `ce94d50` |
| `edutrack` | `edutrack-00018-t58`, 100% | `edutrack:v0.1.0`; `/api/health` 404, version `v0.1.0` |
| Both `the-super-teacher.com` and `www.the-super-teacher.com` | Ready domain mappings to `edutrack` | Version `v0.1.0` |

Direct current candidate target:
`https://superteacher-vbufkr2qma-uc.a.run.app`. Current immutable digest:
`gcr.io/portfolio-383615/superteacher@sha256:e9757073f09b46f0b3b9f01d056e12c8cdc63978d660d44bebbab079c4a39b72`.
The ready revision was created at 04:47 UTC. This supersedes the older
`c344911` observations in `RELEASE_PLAN.md`.

Both services use `292025398859-compute@developer.gserviceaccount.com`.
That identity has project `roles/editor` and
`roles/secretmanager.secretAccessor`, plus bucket-scoped object admin below;
it is not a least-privilege dedicated runtime identity. Changing it requires
preserving current secret and replica access.

Superteacher has 1 vCPU, 512 MiB, concurrency 80, request timeout 300 seconds,
revision maximum one instance, no configured volume or Cloud SQL attachment.
Environment names inspected: `SEED_DEMO_DATA`, `VERSION`,
`LITESTREAM_REPLICA_URL`, `AUTH_PASSWORD`, `SESSION_SECRET`,
`ANTHROPIC_API_KEY`. The latter three reference their existing Secret Manager
names; each currently has enabled version `1`. Other environment values were
not printed. Cloud SQL project inventory is empty and
`superteacher-database-url` is absent.

## Historical initial persistence inventory (04:50 UTC)

Fresh `origin/main` is `ce94d5062a77fce2acfa8e698ecc0082ecc311cb`.
Its accepted `docs/adr/0001-persistence.md` selects the Litestream pilot.
Retaining this path needs no new Cloud SQL instance.

The live non-secret replica URI is
`gs://portfolio-383615-superteacher-litestream/superteacher`.
Bucket metadata: Standard, US-CENTRAL1, uniform bucket-level access, enforced
public-access prevention, object versioning enabled, 7-day soft delete, and
14-day deletion of noncurrent objects. Its explicit policy has no `allUsers`
or `allAuthenticatedUsers`; the runtime identity has `roles/storage.objectAdmin`.
Legacy project owner/editor/viewer grants remain. Metadata inventory found
12 LTX objects totaling 34,483 bytes, updated between 04:47 and 04:49 UTC.
These prove replica objects exist, not restore correctness or a guaranteed RPO.
No object payload was downloaded.

Origin's entrypoint restores before starting the app and exits on restore
errors. It also allows first boot when no replica exists, so a typo in a
production prefix can create an empty dataset: verify the exact URI before
deployment. Keep the native Cloud Run SQLite guard compatible only with the
explicit validated replication branch. Keep demo seeding disabled.

## Safe staged execution

1. Root integrates current main, reconciles entrypoint/configuration and runs
   checks on the actual immutable release. Native integrity migration `0002`
   must remain intact; identity integration has its separate migration issue
   documented in `IDENTITY_INTEGRATION.md`.
2. Build the image without running either existing `cloudbuild.yaml` deploy
   step. The resolved YAML is now build-only; incoming origin YAML deployed straight
   to serving traffic. Build-only command after source checks:

   ```bash
   task_release_sha=$(git rev-parse HEAD)
   /home/jkail/.local/bin/agent-heavy-check -- gcloud builds submit --project=portfolio-383615 \
     --tag="gcr.io/portfolio-383615/superteacher:${task_release_sha}" .
   ```

3. Deploy and verify a separate `superteacher-staging` service with an isolated
   replica prefix and synthetic data. The staging service must never use the
   live prefix. Keep current secret references, runtime account, single-writer
   limits, timezone and proxy settings explicit:

   ```bash
   gcloud run deploy superteacher-staging --project=portfolio-383615 \
     --region=us-central1 --image="gcr.io/portfolio-383615/superteacher:${task_release_sha}" \
     --service-account=292025398859-compute@developer.gserviceaccount.com \
     --allow-unauthenticated --max-instances=1 --min-instances=0 --memory=512Mi --cpu-boost \
     --set-secrets='AUTH_PASSWORD=superteacher-auth-password:1,SESSION_SECRET=superteacher-session-secret:1,ANTHROPIC_API_KEY=anthropic-api-key:1' \
     --set-env-vars="SEED_DEMO_DATA=false,VERSION=${task_release_sha},FORWARDED_ALLOW_IPS=*,SCHOOL_TIMEZONE=UTC,LITESTREAM_REPLICA_URL=gs://portfolio-383615-superteacher-litestream/staging-${task_release_sha}"
   ```

   Use the returned staging URL for health/version, protected 401, authenticated
   workflows, fault rollback and persistence across replacement. Reconcile UTC
   with the selected school timezone before promoting.
4. Before live migration, capture a private consistent restore/export and
   validate a copy with native `superteacher.backup`. Record source URI,
   timestamp, schema version, row counts and integrity outcomes without student
   contents. Rehearse the new migration on that copy. Preserve the original
   replica and restore point throughout the recovery window.
5. `scripts/deploy_cloud_run.sh` requires an explicit service and replica prefix.
   Undrained staging is restricted to the named isolated candidate service,
   isolated prefix and operator isolation acknowledgment. Every shared-prefix
   stage and every promotion requires observed writer-drain evidence. The
   helper checks the recorded serving revision before building and again before
   deploying a shared-prefix candidate. Deployment flags do not suppress
   Litestream restore/replication when a candidate is later invoked. Confirm
   that no other revision writes the selected prefix, including old staging
   revisions. Promotion privately verifies the candidate has exactly one literal
   replica URL matching the supplied bucket/prefix before changing traffic.
   Use the independently verified isolated service for checks. Isolation and
   final drain remain observed operator evidence, not facts this helper proves.
6. Establish a maintenance/quiesce interval that stops new writes and closes
   existing chat sessions; verify the old writer has drained and final replica
   sync completed before starting the new writer. Traffic movement alone does
   not prove this: revision maximum-one does not prevent rollout overlap.
   The script checks the recorded serving revision against the operator
   precondition; it cannot observe writer termination or final sync itself.
   Production promotion still requires that concrete drain step to be observed. Then direct
   100% to the named candidate revision and run authenticated persistence
   verification. Record revisions explicitly instead of `--to-latest`.
7. Rollback must account for schema compatibility. The observed existing replica
   uses independently published accounts `0002`; native head is combined `0003`.
   Recheck the exact old image's supported chain rather than relying on historical
   `ce94d50` evidence. Prepare a compatible rollback image, or restore
   into a separate recovery prefix with a recorded policy for writes since
   cutover. Do not overwrite the live replica to roll back an image.
8. Keep custom domains on `edutrack` until the above is verified. Afterward,
   execute the selected domain cutover while retaining the previous routing
   metadata. Domains and direct service presently serve different products.

[Cloud Run deployment health-check documentation](https://docs.cloud.google.com/run/docs/deploy-functions#disabling_the_deployment_health_check)
describes the default startup invocation; the installed CLI exposes
`--no-deploy-health-check`.
[Cloud Run autoscaling documentation](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
explains revision overlap during deployment.

## Legacy export and remaining evidence

The initial read-only inspection found that legacy public OpenAPI metadata lists `/api/db/classes`, class sections/students,
`/api/db/students/{student_id}` and student grades. It exposes no backup/export
route. A reviewed export must traverse those read endpoints into private
storage, preserve IDs/schema/grades, and check consistency while writes are
quiesced; alternatively capture its actual underlying storage using its own
supported administrative path. A later authorized API archive is now retained
privately, with limits and durable-copy evidence in `LEGACY_CUTOVER.md`. Historical
ADR log observations suggest sample-data initialization, but they do not prove
the current service has no records worth preserving. Do not delete/restart it
based solely on that assertion. Its old image availability must also be checked
before promising an old-image rollback.

Litestream restore of the live prefix into a restricted **new local file** is
the current Superteacher export path. Run the pinned Litestream tool with a
read-authorized identity; never restore over the live file, launch a writer on
the source replica, print records, or upload them into task notes. Save the
snapshot outside the repository. The schema-only production-copy diagnostic
succeeded and the corrected helper passed the private-copy artifact rehearsal
above. Final post-drain adoption and production recovery still need their own
execution evidence. Isolated staging restoration is already verified above.

## Cost and optional PostgreSQL preview

The existing pilot avoids a new always-on database bill. Illustrative GCS cost
before free allowances: 1 GiB Standard in us-central1 plus 100,000 Class A and
100,000 Class B operations is approximately $0.56/month ($0.02 + $0.50 + $0.04),
excluding additional versions, soft-deleted data, network and Cloud Run/AI.
Usage is not inferred from the small metadata inventory.
[Google Storage pricing](https://cloud.google.com/storage/pricing) supplies rates.

If PostgreSQL is later selected, current list-rate arithmetic for the proposed
1-vCPU/3.75-GiB dedicated Enterprise tier at 730 hours is $49.31 compute, plus
about $3.40 for 20 GiB SSD: approximately $52.71/month before backups/network
and other charges. At 100 GiB SSD the corresponding subtotal is $66.31.
This is an optional new recurring cost, not needed for the retained pilot.
[Google Cloud SQL pricing](https://cloud.google.com/sql/pricing) supplies
$0.0413/vCPU-hour, $0.007/GiB-hour and SSD rates; recalculate the exact selected
edition/region in the calculator before execution.

`infra/cloud-sql` remains an optional preview. No Terraform executable was found
on PATH in this pass. Its dry-plan prerequisites are supported Terraform,
verified ADC/impersonation, explicit runtime identity, and reconciliation with
the existing `portfolio-383615-terraform-state` bucket/stack owner. No state
objects were read. Use the isolated preview flow in `CLOUD_SQL_PLAN.md`, including
the deliberately invalid preview credential, without apply/destroy/plan output.
Do not provision it merely to deploy the accepted Litestream branch.
