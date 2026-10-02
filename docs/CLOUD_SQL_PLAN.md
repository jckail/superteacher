# Durable PostgreSQL infrastructure proposal

Status: reviewable infrastructure only. No resources were provisioned, no database
contents accessed, and no Cloud Run revision, traffic allocation, domain mapping,
or existing service account changed. The proposed resources are in
[`infra/cloud-sql`](../infra/cloud-sql). Release configuration remains a separate
step described in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Verified starting point

On 2026-10-01, read-only inspection found no Cloud SQL instances in
`portfolio-383615` / `us-central1`. The active gcloud credential was verified
without exposing credential material; its current configuration has no default
project, so all commands and Terraform explicitly specify the project.
Custom domains currently point to the legacy `edutrack` service. The separate
`superteacher` service's inspected image/revision (`c344911`) has no database URL,
Cloud SQL attachment, or persistent volume. This proposal does not assume either
service is the intended production release target.

The repository's `cloudbuild.yaml` requires `_CLOUD_SQL_INSTANCE` and consumes
`superteacher-database-url` from Secret Manager. Terraform creates that secret with
a SQLAlchemy psycopg URL using `/cloudsql/PROJECT:REGION:INSTANCE` as its Unix
socket host. It does not modify Cloud Build or deploy the app.

## Proposed resources

| Choice | Proposed setting | Decision before provisioning |
| --- | --- | --- |
| Project / region | `portfolio-383615` / `us-central1` | Confirm residency and billing owner. |
| Database | PostgreSQL 17, Enterprise edition | Confirm version/edition before creation. |
| Capacity | `db-custom-1-3840` (1 vCPU, 3.75 GiB) | Confirm budget; measure workload before resizing. |
| Availability | `ZONAL` | Choose `REGIONAL` for standby and zone failover when required. |
| Storage | 20 GB SSD, automatic growth capped at 100 GB | Approve ceiling and monitor disk usage; a full disk can interrupt service. |
| Backups | Daily at 10:00 UTC, 14 retained backups in `us-central1` | Confirm retention; same-region backups are not a cross-region recovery strategy. |
| PITR | Enabled; 7 days of transaction logs | Agree recovery objectives and rehearse restoration. |
| Maintenance | Sunday 11:00 UTC, stable rollout | Confirm a suitable maintenance window; restarts can interrupt connections. |
| Deletion protection | Cloud SQL API protection, Terraform protection, `prevent_destroy` | Leave enabled; removal requires a separately reviewed deliberate change. |
| Connectivity | Public IP, no authorized networks, connector required, encrypted connections | Matches Cloud Run's existing Unix socket integration without a new VPC. |
| Runtime identity | Required explicit existing service account | Inspect the chosen service's runtime identity; do not guess or use a deployment identity. |
| Secret replication | User-managed in `us-central1` | Confirm regional residency and availability requirements. |

Cloud SQL Auth Proxy/connector connections authenticate with IAM and do not need
authorized networks. This module rejects direct database connections and uses
the per-instance CA compatible with Cloud Run's built-in proxy. Private IP is an
alternative if required by policy; it needs a reviewed VPC/private services access
and Cloud Run egress design, rather than simply switching off public IP.
[Cloud Run connection documentation](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
describes the supported paths.

The Cloud SQL settings and PostgreSQL version are supported by the
[Google provider resource reference](https://registry.terraform.io/providers/hashicorp/google/7.22.0/docs/resources/sql_database_instance).
Dedicated capacity incurs ongoing cost while provisioned, even without requests.
Budget for CPU/RAM, SSD storage, backups/logs, applicable network transfer, and
Secret Manager operations. Regional HA adds a standby and increases cost.
Obtain a current estimate from the
[Google Cloud pricing calculator](https://cloud.google.com/products/calculator)
using both ZONAL and REGIONAL scenarios; no price estimate is treated as approved.

## Identity and PostgreSQL privilege prerequisites

Terraform adds `roles/cloudsql.client` on the project and
`roles/secretmanager.secretAccessor` on **only** `superteacher-database-url` to the
explicitly supplied runtime account. These are additive IAM members, preserving
existing grants. It grants no SQL administrator, project editor, or blanket
Secret Manager role. Cloud SQL client is project-scoped and consequently permits
connector access to other Cloud SQL instances in that project; SQL credentials
still govern database access. Use a dedicated project if that scope is unacceptable.

The chosen runtime account separately needs access to the app's existing auth,
session, and AI secrets; this module does not change those grants. An operator
must inspect the existing account and the chosen Cloud Run service before any
provisioning or deployment:

```bash
gcloud run services describe superteacher \
  --project=portfolio-383615 --region=us-central1 \
  --format='value(spec.template.spec.serviceAccountName)'
gcloud iam service-accounts describe EXISTING_RUNTIME_SERVICE_ACCOUNT_EMAIL \
  --project=portfolio-383615 --format='value(email)'
```

The infrastructure operator needs separate reviewed permissions to enable APIs,
manage Cloud SQL instances/users/databases and Secret Manager, and add the scoped
IAM members. Cloud Run runtime permissions are insufficient for provisioning.
Terraform authenticates using ADC or approved service-account impersonation;
gcloud's active login alone does not prove Terraform ADC exists.

**Mandatory before any release:** Cloud SQL's Admin API initially grants built-in
PostgreSQL users `cloudsqlsuperuser` when no custom database roles exist.
Terraform alone here does not create in-database SQL roles. The new database is
empty, and the application account must be hardened through an independently
approved administrator connection using Cloud SQL Auth Proxy before running any
app against it. This is a documented Cloud SQL behavior, not a least-privilege SQL
claim. [User management documentation](https://docs.cloud.google.com/sql/docs/postgres/create-manage-users)
explains custom-role prerequisites.

For the default names, the administrator's proposed SQL is:

```sql
-- Run as the database administrator against the new instance, not a legacy DB.
ALTER DATABASE superteacher OWNER TO superteacher_app;
REVOKE cloudsqlsuperuser FROM superteacher_app;
ALTER ROLE superteacher_app NOCREATEDB NOCREATEROLE NOREPLICATION;
REVOKE ALL ON DATABASE superteacher FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE superteacher TO superteacher_app;
-- Reconnect to the superteacher database before the following statements.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO superteacher_app;
GRANT USAGE, CREATE ON SCHEMA public TO superteacher_app;
```

This confines ownership and startup migration DDL to the app's own database and
schema. Verify role attributes, role memberships, database ownership, and denied
access to unrelated databases before releasing. PostgreSQL's built-in `postgres`
and other databases may still have PUBLIC CONNECT: explicitly review/revoke that
access if the deployment requires isolation. Do not revoke grants on shared
databases without inspecting dependencies. A future migration-job design can
separate a schema-owning migration user from a runtime DML-only user; the current
app's startup migrations require schema ownership. Provision an administrator
credential outside this module if needed; never expose it to Cloud Run.

## State, credentials, and safe dry runs

Requires Terraform `>= 1.11, < 2` and Google provider `>= 7.22, < 8`. The committed
lock file selects the provider version validated during preparation. Review any
lock-file upgrade explicitly. The password variable is ephemeral; SQL user
`password_wo` and secret-version `secret_data_wo` are write-only. The password and
derived URL are not persisted in state or saved plans. Increment
`credential_version` for a deliberate rotation of both. Supply the same approved
password again at execution; Terraform cannot recover it from state.
[Terraform sensitive-data guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
and the [provider secret-version reference](https://registry.terraform.io/providers/hashicorp/google/7.22.0/docs/resources/secret_manager_secret_version)
describe these features.

State still contains infrastructure metadata and IAM identities and must be
treated as sensitive. No backend is configured to avoid creating or assuming a
storage bucket. Before an approved apply, select a restricted encrypted remote
state backend with locking, versioning and narrowly scoped access; add its backend
configuration and review the initialization/migration separately. Local state,
variable files and plan snapshots are ignored within `infra/cloud-sql`. Do not
enable verbose provider logging, commit secrets, or store real values in shell
history, `.tfvars`, tickets, artifacts, or the repository.

The following isolated validation commands do not use credentials or contact
Cloud SQL. Substitute a locally installed supported Terraform executable as
needed. Run from the repository root:

```bash
terraform fmt -check infra/cloud-sql
task_tf_review_dir=$(mktemp -d /tmp/superteacher-tf-review.XXXXXX)
chmod 700 "$task_tf_review_dir"
cp infra/cloud-sql/*.tf infra/cloud-sql/.terraform.lock.hcl "$task_tf_review_dir/"
terraform -chdir="$task_tf_review_dir" init -backend=false -input=false -lockfile=readonly
terraform -chdir="$task_tf_review_dir" validate
```

For a **read-only infrastructure plan**, first verify the active credential and
target and confirm ADC is available. This lists instance metadata without opening
databases or secret payloads:

```bash
gcloud auth list --filter=status:ACTIVE --format='value(status)'
gcloud sql instances list --project=portfolio-383615 \
  --filter='region:us-central1' --format='table(name,region,databaseVersion)'
gcloud secrets describe superteacher-database-url \
  --project=portfolio-383615 --format='value(name)'
```

A missing secret is expected for a new setup. If it exists, stop and inspect
ownership and replication metadata before adopting it; do not read its payload
as part of this plan. For a new-resource preview in the isolated directory above:

```bash
read -r -p 'Confirmed existing runtime service-account email: ' TF_VAR_cloud_run_service_account_email
export TF_VAR_cloud_run_service_account_email
# Deliberately invalid for deployment: preview only, never apply this credential.
export TF_VAR_database_password='PREVIEW_ONLY_DO_NOT_APPLY_24_PLUS_CHARS'
terraform -chdir="$task_tf_review_dir" plan -input=false -detailed-exitcode \
  -var='project_id=portfolio-383615' -var='region=us-central1'
# Exit 2 means proposed changes; exit 1 means an error; exit 0 means no changes.
unset TF_VAR_database_password TF_VAR_cloud_run_service_account_email
```

Do not add `-out`, `apply`, or `destroy` to this review workflow. If resources
already exist but are absent from the isolated state, this preview is incomplete:
first use the approved backend and reconcile/import ownership. For an authorized
future execution, replace the preview credential via a secure secret source or
`read -r -s` into the ephemeral environment variable, then unset it promptly.
Credential rotation needs a staged maintenance/release plan: PostgreSQL password
changes invalidate old credentials, while `latest` moves to the new secret version.
Pin the reviewed secret version for a staged revision and recycle old connections;
there is no automatic zero-downtime password-rotation guarantee here.

## Adoption, restore, and release gates

1. Confirm budget, residency, availability, retention, runtime identity, intended
   release service, and state-backend owner. Review the actual plan and reject
   unexpected replacements/deletions or unrelated IAM changes.
2. If resources appeared since inspection, do not recreate them. Confirm they are
   not managed by another stack. Import the instance, database, user, secret and
   IAM members into the approved state and reconcile configuration before apply.
   Never blindly import a secret version: verify write-only handling first; an
   imported ordinary secret version can expose payloads to state. Examples of
   resource import identifiers (not commands executed during preparation):

   ```text
   google_sql_database_instance.app: projects/portfolio-383615/instances/superteacher-postgres
   google_sql_database.app: projects/portfolio-383615/instances/superteacher-postgres/databases/superteacher
   google_sql_user.app: portfolio-383615/superteacher-postgres/superteacher_app
   google_secret_manager_secret.database_url: projects/portfolio-383615/secrets/superteacher-database-url
   ```

3. After separate approval, provision infrastructure; harden and verify the SQL
   user before deploying. Terraform does not populate tables, execute migrations,
   copy legacy SQLite files, or access student records.
4. Establish a verified export/source snapshot and a reviewed migration mapping
   before moving existing data. Confirm access authorization and preserve the
   original source until validation and the recovery window are complete. For a
   new empty database, run the app's Alembic migrations with demo seeding disabled.
5. Rehearse backup/PITR restoration to a **separate instance**, verify the recovery
   point and integrity, harden roles on the restored instance, and reconcile its
   infrastructure state. Restore actions are intentionally absent from Terraform
   because restore-on-update can overwrite data. Review the new connection name
   and secret version before any cutover. [Cloud SQL backup overview](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
   distinguishes backups from recovery operations.
6. Attach Cloud SQL and the exact secret version to a staged Cloud Run revision
   with the confirmed runtime account; test migrations, readiness, login, write
   persistence across revision restart, and rollback against synthetic data.
   Approve production traffic and domain changes separately. An empty new
   database does not prove legacy records were preserved.

## Validation performed

Validated locally using Terraform 1.13.5 (temporary binary; official release
checksum verified) and signed `hashicorp/google` 7.46.1, locked in the committed
provider lock file. `terraform fmt -check` and `terraform validate` passed after
`init -backend=false` in an isolated temporary directory. No real password was
generated, no plan snapshot/state file written into the repository, and no
infrastructure `plan`, `apply`, restore, or deployment was executed. Provider
schema validation verifies syntax and field compatibility, not billing approval,
permissions, available regional capacity, or application/database connectivity.
