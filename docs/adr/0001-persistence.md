# ADR 0001: Production persistence

- Status: Proposed, needs owner decision
- Date: 2026-10-02
- Deciders: Jordan Kail (owner)
- Blocks: ADR 0005 (domain cutover). Do not point real users at the new service until this is resolved.

## Context

Super Teacher stores grades, attendance and teacher notes for real students. Today the `superteacher` Cloud Run service
(revision `superteacher-00002-b5n`, `maxScale=1`, 1 vCPU / 512 Mi, request-based CPU, no volumes, no min-instances;
read from `gcloud run services describe`, 2026-10-02) keeps its SQLite file at `/data/superteacher.db`
(`Dockerfile`: `DATABASE_URL=sqlite:////data/superteacher.db`). **That path is the container's writable layer. Cloud Run
instances are ephemeral: any scale-to-zero, redeploy, crash or host move silently discards every teacher's data.** The
`cloudbuild.yaml` comment says "SQLite needs a single writer, hence max-instances=1" but nothing makes the file durable;
`docs/DEPLOYMENT.md` only mentions the options in one paragraph.

Facts about the app that constrain the choice (from `superteacher/db.py`, `models.py`, `main.py`, `alembic/`):

- SQLAlchemy 2 + Alembic. Migrations run at startup (`run_migrations` in the lifespan hook), so every cold start pays migration time.
- Schema is small: courses, sections, students, assessments, scores, attendance, notes, insights. Expected data is megabytes per teacher.
- Workload is read-heavy with short writes (score entry, attendance, notes). One chat WebSocket per active teacher.
- Auth lockout state is in process memory and the session secret falls back to a file next to the DB, so the app already
  assumes one instance (fine for now, see ADR 0002 for the identity change).
- Observed cold start of the new service: one first request after idle took about 20 s end to end (single sample on 2026-10-02,
  `curl` to `/api/health`; warm requests are about 0.13 s). Whatever we pick adds to that.

SQLite-specific items to check for any non-SQLite option (code is not changed by this ADR):

| Location | SQLite-ism | Effect on Postgres |
|---|---|---|
| `db.py` `make_engine` | `check_same_thread`, `PRAGMA foreign_keys=ON` | Already guarded by `startswith("sqlite")`. Nothing to do. |
| `db.py` `is_memory`, `run_migrations` | in-memory tests use `create_all`, files use Alembic | Works for Postgres (goes through Alembic). Tests should add a Postgres job (testcontainers or a CI service container). |
| `alembic/env.py` | `render_as_batch` only for sqlite | Already conditional. |
| `alembic/versions/0001_initial_schema.py` | `sa.Enum(..., name='assessmentkind')` | On Postgres this creates native ENUM types; `downgrade` must drop them; future enum changes need `ALTER TYPE`. Consider `native_enum=False` before the first Postgres deploy. |
| `models.py` | `DateTime(timezone=True)` columns; `JSON` | SQLite returns naive datetimes; Postgres returns aware ones. Check any comparison of `created_at` with naive values. `JSON` maps to `json` (use `JSONB` if we ever query inside it). |
| `queries.py` | `Student.name.ilike(...)` | Portable (SQLAlchemy emits `ILIKE`). Note SQLite `LIKE` is ASCII-case-insensitive only; Postgres `ILIKE` is full Unicode. Behaviour improves. |
| `routers/roster.py` | `func.lower(name) == name.lower()` for uniqueness | Portable, but the DB-level `UNIQUE(name)` on `courses` is case-sensitive on Postgres and global (relevant to ADR 0002, it blocks two teachers having a course called "Algebra 1"). |
| `models.py` ids | `String(12)` random hex, app-generated | Portable. |
| `config.py` / `auth.py` | `.session_secret` file next to the SQLite DB | Not used when `SESSION_SECRET` is set (it is, via Secret Manager). |
| `requirements.txt` | no Postgres driver | Add `psycopg[binary]` (v3) or `pg8000`; URL becomes `postgresql+psycopg://`. |
| Connection pool | SQLite uses a static/queue pool | Postgres needs `pool_size` small (2 to 5) and `pool_pre_ping=True`; Cloud Run scale-out multiplies connections. |

## Options

### (a) SQLite plus Litestream replicating to a GCS bucket, `max-instances=1`

Litestream ships WAL frames to `gs://bucket/path` continuously and restores the database on boot with
`litestream restore -if-db-not-exists -o /data/superteacher.db gs://...`. On Cloud Run it picks up credentials from the
metadata server (Litestream GCS guide, https://litestream.io/guides/gcs/, read 2026-10-02). The container runs
`litestream replicate -exec "python server.py"` so Litestream supervises the app and does a final sync on SIGTERM.

Pros
- Smallest change: no app code change at all, only Dockerfile, a `litestream.yml`, a bucket and IAM (`roles/storage.objectAdmin` on one bucket for the runtime service account).
- Keeps the zero-ops, zero-network-hop SQLite performance. Works with the current Alembic migrations unchanged.
- Cost is pennies.
- Point-in-time restore is possible within the retention window; the replica is also an off-instance backup.

Cons and honest hazards
- **RPO is not zero.** Replication is asynchronous (default 1 s sync interval). With Cloud Run's default request-based CPU
  billing, CPU is throttled outside requests, so background replication can stall between requests. A SIGTERM gives about 10 s
  to flush. A hard kill (OOM, host failure) loses the unsynced tail. Realistic RPO: seconds under normal use, minutes in the
  worst case. Setting CPU to "always allocated" fixes the throttling at about $49/month (estimate, see Cost).
- **Overlapping instances during a rollout.** `maxScale=1` is per revision. While traffic shifts to a new revision the old and
  new instance can both run for a short time, and both would replicate to the same path. That forks Litestream generations and
  can lose writes made on the old instance. Mitigation: deploy with a documented procedure (see Migration/rollback), or pick a
  replica path per revision plus a promotion step. This is the single biggest operational risk of option (a).
- Single writer ceiling: one instance, one CPU. Fine for tens of teachers; a hard limit before hundreds of concurrent users.
- Every cold start restores from GCS before serving. For a few MB this is 1 to 3 s (estimate; measure it) but it is added to the
  observed 20 s cold start. Mitigate with `min-instances=1` (about $10 to $50/month depending on billing mode) or accept it.
- Restore failure modes must fail closed: if the restore errors, the container must refuse to start rather than create an empty
  database over the top of a good replica.
- Litestream is a small open source project maintained by one company/author; it has changed major versions (v0.5 in 2025). Pin the version.

### (b) Cloud SQL for PostgreSQL

Smallest viable tiers (Enterprise edition, us-central1; Cloud SQL pricing page https://cloud.google.com/sql/pricing and
third-party summaries, read 2026-10-02; the pricing page itself did not render rates, so rates below come from secondary
sources and must be checked in the pricing calculator):

- `db-f1-micro` shared core: about $0.0105/h, roughly $7.7/month. 0.6 GB RAM, **no SLA**, intended for dev.
- `db-g1-small` shared core: about $0.035/h, roughly $25.6/month. 1.7 GB RAM, no SLA.
- 1 dedicated vCPU / 3.75 GB (`db-custom-1-3840`): roughly $45 to $50/month (estimate from list rates in memory, verify).
- SSD storage $0.17/GB-month, HA doubles it. Automated backups and PITR (WAL archiving) are included in the tier, backup storage is billed per GB.
- HA (regional, synchronous standby) about doubles instance cost. Shared-core HA is quoted by one source; confirm in console.

Connectivity: Cloud Run to Cloud SQL via the built-in Cloud SQL connector (`--add-cloudsql-instances`, Unix socket, IAM or password
auth) works with a public IP restricted by the connector, no VPC needed. Private IP needs Direct VPC egress on Cloud Run
(no connector VM cost). Public IPv4 addresses on Cloud SQL carry a small hourly charge (about $7/month, verify).

Pros
- Real durability: automated daily backups, PITR to the second within the retention window, optional HA with RPO about 0 and RTO about 1 to 2 minutes.
- Removes the single-instance constraint: `max-instances` can rise, which also unlocks multi-instance auth state work (ADR 0002).
- Needed anyway once there are multiple teachers writing concurrently, per-tenant row filters and reporting queries.
- Same Google project, IAM, audit logs, one data processor (matters for ADR 0003).

Cons
- Always-on cost floor of $9 to $30 even at one teacher; HA about $100.
- Code work: driver, pool settings, enum handling, Postgres CI job, Alembic first run on Postgres, data migration script from SQLite. About 1 to 2 days (estimate).
- Cold start gains a connection handshake (about 100 to 300 ms) but no restore. Shared-core instances can be CPU throttled under load.
- Operational: maintenance windows, version upgrades, connection limits (`db-f1-micro` allows few connections, keep the pool small).
- There is currently no Cloud SQL instance in the project (`gcloud sql instances list` returned none, 2026-10-02), so this is net new infrastructure.

### (c) GCS FUSE volume mount with SQLite

Cloud Run can mount a bucket as a volume. Google's own documentation is explicit: Cloud Storage FUSE "does not provide
concurrency control for multiple writes (file locking) to the same file. When multiple writes try to replace a file, the last
write wins and all previous writes are lost", it is "not a fully POSIX-compliant file system", writes are staged in memory and
only flushed on `close()`/`fsync()`, and mount adds start-up time with a 30 s mount timeout
(https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts, read 2026-10-02).

SQLite needs byte-range locks, atomic rename/journal semantics and, in WAL mode, shared memory (`-shm` mmap) that FUSE object
stores cannot provide. Rollback-journal mode might appear to work with one writer, but a crash between journal write and flush,
or the overlap during a rollout (two instances, last writer wins on the whole object), corrupts or silently rolls back the file.
Every commit rewrites the entire database object. **Not recommended**, and the current `docs/DEPLOYMENT.md` suggestion of it should be removed. RPO is undefined, RTO is a restore from object versioning if enabled.

### (d) Filestore / NFS volume

Cloud Run supports NFS mounts (Filestore) with real file semantics, and SQLite over NFS with `max-instances=1` can work, but:
Filestore needs a VPC, minimum capacity on the Basic tiers is 1 TiB (about $200/month for Basic HDD, estimate, verify), and SQLite
over NFS is documented by SQLite itself as unreliable because of lock implementations. Cost is 20 to 30 times higher than option (a)
for no durability benefit over Litestream. **Rejected on cost and risk.**

### (e) Managed serverless Postgres (Neon, Supabase)

- Neon (https://neon.com/pricing, read 2026-10-02): Free plan has 100 CU-hours, 1 GB, 6 h point-in-time restore, scale to zero
  after 5 min (cold resume adds a second or so on first query). Launch is usage based: $0.106 per CU-hour, $0.35/GB-month, 7 day PITR.
  Runs on AWS/Azure, **not on GCP**, so queries cross clouds (about 20 to 40 ms per round trip from us-central1 to us-east, estimate); N+1 patterns in the roster/gradebook code would feel it. A new sub-processor for student data (ADR 0003).
- Supabase (https://supabase.com, plans read 2026-10-02 via secondary summaries): Free pauses after 1 week of inactivity (a classroom app over a school break would pause, data kept but offline until restored) and has 500 MB. Pro is $25/month per project with 8 GB. Project secrets named `supabase-url`, `supabase-anon-key`, `supabase-service-role` already exist in Secret Manager (created 2026-07-09 by Terraform, names only checked, values not read). They almost certainly belong to the portfolio site, not Super Teacher, and the "service role" key bypasses row-level security, so **do not reuse that project**. A separate project would be needed.
- Pros: PITR and branching, scale to zero on Neon, no instance to size.
- Cons: second vendor and second bill, cross-cloud latency and egress, data residency/sub-processor review for children's data, same code work as option (b). It gives few advantages over Cloud SQL for a project already on GCP.

### (f) Firestore rewrite

**Rejected.** The domain is relational (course, section, student, assessment, score, attendance) and the app depends on joins and aggregates
(`metrics.py`, `queries.py`, reports, CSV). Firestore has no joins, weak aggregation, per-document write limits, and would need a
rewrite of the ORM layer, Alembic, every router and every test (weeks, not days), plus re-deriving unique constraints in application code.
It buys serverless scaling the app does not need. It would also lose the ability to run the same schema locally and in CI.

## Cost (monthly, estimates)

Common to all options: Cloud Run compute. Request-based billing is $0.000024 per vCPU-s and $0.0000025 per GiB-s with a free tier of
180k vCPU-s and 360k GiB-s per month (Cloud Run pricing via secondary summary, 2026-10-02). Assumed active time 20 h, 200 h, 1,500 h per
month for 1 / 10 / 100 teachers, giving roughly $0 / $5 / $30 (estimate, requests overlap so real time is lower). Anthropic API usage is excluded and is the same for every option.

| Option | 1 teacher | 10 teachers | 100 teachers | Assumptions |
|---|---|---|---|---|
| (a) Litestream/GCS, request-based CPU | about $0 to 1 | about $1 | about $3 | DB under 5 MB per teacher; GCS $0.02/GB-month, a few thousand to a few hundred thousand writes ops; snapshots retained 7 days |
| (a) with CPU always allocated (tight RPO) | about $49 | about $49 | about $50 | 1 vCPU x 2.59 M s x $0.000018 plus 0.5 GiB x $0.000002, estimate; a single always-on instance |
| (b) Cloud SQL `db-f1-micro` (dev grade) | about $10 | about $10 | not suitable | $7.7 instance + 10 GB SSD $1.7 + backups, no SLA |
| (b) Cloud SQL `db-g1-small`, no HA | about $28 | about $28 | about $30 | $25.6 + 10 GB SSD $1.7 + backups |
| (b) Cloud SQL 1 vCPU dedicated, HA | about $105 | about $105 | about $110 | roughly 2 x $50 + storage; estimate, verify in calculator |
| (c) GCS FUSE | about $1 | about $2 | about $5 | cost is not the issue; correctness is. Rejected |
| (d) Filestore Basic HDD 1 TiB | about $200 | about $200 | about $200 | minimum capacity, estimate |
| (e) Neon Launch | about $1 to 3 | about $3 to 6 | about $20 to 25 | 0.25 CU, scale to zero, 1 to 10 GB at $0.35 |
| (e) Supabase Pro | $25 | $25 | $25 to 35 | per project, 8 GB included |

## Comparison

| | RPO | RTO | Added cold start | Ops burden | Code change |
|---|---|---|---|---|---|
| (a) Litestream | seconds (minutes worst case), 0 loss on clean SIGTERM | 1 to 5 min (redeploy + restore) | restore 1 to 3 s for MB-sized DB (estimate) | low-medium: rollout overlap procedure, restore drills | none |
| (b) Cloud SQL | about 0 with HA; seconds to minutes (PITR) without | 1 to 2 min HA failover; 10 to 30 min restore from backup | about 0.2 s connect | low (managed), but billed 24/7 | driver, pool, enum, CI, data migration |
| (c) GCS FUSE | undefined | undefined | mount up to 30 s | high (debugging corruption) | none |
| (d) Filestore | near 0 (snapshots hourly) | minutes | NFS mount | medium | none |
| (e) Neon/Supabase | seconds (PITR 6 h to 30 d by plan) | minutes | 0.5 to 2 s on resume | low, extra vendor | same as (b) |
| (f) Firestore | n/a | n/a | n/a | n/a | rewrite |

## Risks

- Choosing (a) and forgetting the rollout-overlap hazard: silent loss of the last minutes of writes at each deploy.
- Choosing (a) with request-based CPU and assuming RPO of 1 s.
- Choosing (b) with `db-f1-micro` for real students: no SLA, no HA, small RAM.
- Any option: backups that are never restore-tested. Both paths need a quarterly restore drill and an alert on replication/backup age.
- Data is children's education records (ADR 0003): bucket or instance location, encryption (Google-managed by default, CMEK optional), IAM least privilege, no public access (`gcloud storage buckets` uniform access, public access prevention).

## Decision needed from the owner

1. Persistence option: (a) Litestream now with a planned move to (b), or (b) straight away?
2. Is an RPO of "seconds, minutes worst case" acceptable for the first pilot, or must it be about zero?
3. Is about $0 to 50/month (a) or about $28 to 105/month (b) the budget envelope?
4. Which region for backups (US multi-region versus `us-central1` single region)?

## Recommendation

Adopt **(a) Litestream to GCS with `max-instances=1` as the gate for a pilot of up to about 10 teachers**, with `min-instances=0`
and a restore-on-boot that fails closed, a versioned and retention-limited bucket in `us-central1`, and a written deploy
procedure that avoids overlapping writers. Plan **(b) Cloud SQL `db-g1-small` (no HA) as the next step**, triggered by any of:
more than about 10 teachers, a second concurrently-active instance needed, per-teacher accounts rollout (ADR 0002), or a customer asking
for a contractual RPO. If the owner would rather not run a restore-on-boot pattern at all, choose (b) now: it costs about
$28/month and avoids the rollout-overlap risk, at the price of 1 to 2 days of code work. Reject (c), (d), (f); (e) is
only worth it if Postgres without GCP is acceptable (it adds a sub-processor).

## Migration and rollback plan

For (a):
1. Create `gs://portfolio-383615-superteacher-litestream` in `us-central1`, uniform bucket-level access, public access prevention, object versioning on, lifecycle delete of noncurrent versions after 14 days.
2. Grant the runtime service account (currently the default compute service account `292025398859-compute@developer.gserviceaccount.com`; a dedicated one is better) `roles/storage.objectAdmin` on that bucket only.
3. Dockerfile: install a pinned Litestream release, entrypoint script: `litestream restore -if-replica-exists -if-db-not-exists`, then `exec litestream replicate -exec "python server.py"`. If restore fails for any reason other than "no replica yet", exit non-zero.
4. Deploy with `--no-traffic`, health check the new revision. To avoid two writers: deploy using a short maintenance step (route 0% to the old revision, wait for its instance to drain, then route 100% to the new one), or set `--max-instances=1` and `--min-instances=0` and shift traffic only after the old revision shows no instances.
5. Drill: write a row, `gcloud run services update` with a trivial env var change to force a new revision, confirm the row survives; then delete the instance and confirm restore.
6. Alert: Cloud Monitoring log-based alert on Litestream errors and on "restore failed".

Rollback: redeploy the previous image (`gcr.io/portfolio-383615/superteacher:c344911`); the replica in GCS is untouched by app code. To go back to ephemeral SQLite is never desirable.

For (b) later: add driver and Postgres CI job, run Alembic against an empty Postgres, write a one-off script that copies tables in dependency order from the Litestream-restored SQLite file (`courses`, `sections`, `students`, `assessments`, `scores`, `attendance`, `notes`, `insights`), compare row counts and a checksum of `metrics.compute` output per student, put the app in read-only for the final copy (a few minutes), switch `DATABASE_URL` secret, keep the Litestream replica for 30 days as rollback.

## Sources (all read 2026-10-02)

- Litestream GCS guide, https://litestream.io/guides/gcs/
- Cloud Run Cloud Storage volume mounts, https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts
- Cloud SQL pricing, https://cloud.google.com/sql/pricing (rates via secondary summaries, verify)
- Neon pricing, https://neon.com/pricing
- Supabase pricing summaries (uibakery, cloudzero, 2026), verify at https://supabase.com/pricing
- Cloud Run pricing, https://cloud.google.com/run/pricing (rates via secondary summaries)
- Project state: `gcloud run services describe superteacher`, `gcloud sql instances list`, `gcloud secrets list` (names only), 2026-10-02
