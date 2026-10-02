# Deployment status and execution handoff

Observed 2026-10-02 04:50 UTC (2026-10-01 Pacific). Deployment is authorized by
the user; this pass prepared the release through read-only cloud metadata and
public health/version/schema inspection. It did not deploy, retrieve secret
payloads or database contents, send email, or change traffic/resources. The root
agent owns release execution and verification.

## Current targets

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

## Durable pilot now exists

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
   gcloud builds submit --project=portfolio-383615 \
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
5. The merged `scripts/deploy_cloud_run.sh` now stages by default and requires
   explicit operator drain evidence for its separate `--promote` command. The
   incoming script claimed `--no-traffic` starts no instance; that is false
   with the default deployment health check: local CLI help says the
   check schedules an instance. The app also writes startup migrations.
   For the production replica, stage with BOTH `--no-traffic` and
   `--no-deploy-health-check`, minimum zero, no tagged URL requests, and no
   production health probes until promotion. Use the independently verified
   staging service for pre-promotion checks.
6. Establish a maintenance/quiesce interval that stops new writes and closes
   existing chat sessions; verify the old writer has drained and final replica
   sync completed before starting the new writer. Traffic movement alone does
   not prove this: revision maximum-one does not prevent rollout overlap.
   The script checks the recorded serving revision against the operator
   precondition; it cannot observe writer termination or final sync itself.
   Production promotion still requires that concrete drain step to be observed. Then direct
   100% to the named candidate revision and run authenticated persistence
   verification. Record revisions explicitly instead of `--to-latest`.
7. Rollback must account for schema compatibility. Current `ce94d50` has only
   migration `0001`; native adds `0002`. That old image may refuse a database
   already stamped `0002`. Prepare a compatible rollback image, or restore
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

Legacy public OpenAPI metadata lists `/api/db/classes`, class sections/students,
`/api/db/students/{student_id}` and student grades. It exposes no backup/export
route. A reviewed export must traverse those read endpoints into private
storage, preserve IDs/schema/grades, and check consistency while writes are
quiesced; alternatively capture its actual underlying storage using its own
supported administrative path. No private endpoint was called here. Historical
ADR log observations suggest sample-data initialization, but they do not prove
the current service has no records worth preserving. Do not delete/restart it
based solely on that assertion. Its old image availability must also be checked
before promising an old-image rollback.

Litestream restore of the live prefix into a restricted **new local file** is
the current Superteacher export path. Run the pinned Litestream tool with a
read-authorized identity; never restore over the live file, launch a writer on
the source replica, print records, or upload them into task notes. Save the
snapshot outside the repository. Its restore rehearsal and release evidence
remain to be executed by the verification owner.

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
