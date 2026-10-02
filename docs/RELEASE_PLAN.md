# Deployment targets and cutover prerequisites

Verified read-only on 2026-10-01 Pacific time. No production resources, traffic, secrets or records were changed during this review. Environment variable names and secret references were inspected; secret values and student records were not retrieved.

| Target | Observed release | Configuration |
| --- | --- | --- |
| `www.the-super-teacher.com` and `the-super-teacher.com` | Cloud Run domain mappings point to `edutrack` in `portfolio-383615`, `us-central1`. Its ready revision is `edutrack-00018-t58`, image `gcr.io/portfolio-383615/edutrack:v0.1.0`. | Public root serves older assets; `/api/version` returns 404. Service has no configured environment variables or mounted volumes. |
| `superteacher-vbufkr2qma-uc.a.run.app` | Separate `superteacher` service, ready revision `superteacher-00002-b5n`, image `gcr.io/portfolio-383615/superteacher:c344911`. | Health returns 200 and version `c344911`; authentication/AI reference secrets. No `DATABASE_URL`, Cloud SQL attachment or mounted storage is configured. |

The direct service and custom domain serve different applications. Deploying only to `superteacher` does not update the existing custom domains. The latest local overhaul has not been published.

The deployed `superteacher` image's source uses SQLite by default, and its configuration has no durable database override or volume. Do not replace/restart it on the assumption that existing records are durable. Current overhaul startup rejects SQLite on Cloud Run. No Cloud SQL instances were returned by the project inventory.

## Prepare a candidate

1. Select the identity/teacher-account model, permitted model data and retention policy. The current passcode grants access to one shared dataset.
2. Review [the validated Cloud SQL Terraform plan](CLOUD_SQL_PLAN.md), then provision a PostgreSQL database with backups and an agreed cost/resource configuration. Supply the Cloud SQL connection and `superteacher-database-url` secret to the existing deployment configuration. The configuration does not provision those resources.
3. Determine whether either deployed application contains records that must be retained; obtain a consistent export/backup and prove import/restore separately before changing any serving revision. No live student-data export was attempted here.
4. Package an immutable source revision and rerun CI: strict TypeScript, lint, backend/PostgreSQL tests, frontend tests, production browser workflows, Docker build and authenticated runtime smoke checks.
5. Build and validate the candidate on the separate `superteacher` service or a dedicated staging target. `_SERVICE_NAME` selects the target explicitly; it defaults to `superteacher`. Verify database identity, schema version, record counts, authentication and version before moving public traffic.

## Review a public cutover

Two alternatives require an explicit choice once the candidate and data preparation are verified:

- Deploy the reviewed app to the currently mapped `edutrack` service, preserving the existing domain mappings. Record the previous revision and rollback command first; stage/test the new revision before shifting traffic.
- Keep the new app on `superteacher` and change both domain mappings. Review certificate/routing behavior and outage risk before replacing a mapping; do not assume an in-place route update is supported.

Keep the prior service/revision available during verification. Check both domains for the expected `/api/version`, public health, protected API 401, login, persisted records, safe AI fallback and mobile UI. Rollback application traffic without deleting the new database or discarding any newly written records.

Cloud Run mapping inventory was read using Google's [domain mapping API](https://docs.cloud.google.com/run/docs/reference/rest/v1/namespaces.domainmappings). This document records observed targets and preparation work, not permission to change live traffic.
