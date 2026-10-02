# Deployment

Super Teacher holds student data, so it ships with authentication on by default and refuses to start
without it.

## Authentication model

One shared passcode (`AUTH_PASSWORD`) for a single teacher or a small school. There is no user table.

* `POST /api/auth/login` checks the passcode in constant time and sets a signed, `HttpOnly`,
  `SameSite=Lax` cookie (`Secure` automatically on https / `X-Forwarded-Proto: https`).
  `POST /api/auth/logout` clears it; `GET /api/auth/me` reports the session (401 if none).
* Every `/api` route and the chat WebSocket require the cookie. Only `/api/health`, `/api/version` and
  `/api/auth/*` are public.
* CSRF: state-changing requests need an `X-Requested-With` header (the web app sends it) and any `Origin`
  header must be same-host or listed in `CORS_ORIGINS`. The WebSocket handshake gets the same origin check.
* Brute force: 5 wrong passcodes from one address start an exponential lockout (15s, 30s, ... max 15min,
  HTTP 429 + `Retry-After`); a global limiter backs this up. State is in memory per instance.
* Changing `AUTH_PASSWORD` invalidates all existing sessions. Sessions last `SESSION_TTL_HOURS` (12).
* Responses carry CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`/`frame-ancestors 'none'`.
  `/api/docs` is off unless `ENABLE_DOCS=true`.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `AUTH_PASSWORD` | none | **Required** unless `AUTH_DISABLED=true`. Use a long random value. |
| `AUTH_DISABLED` | `false` | `true` runs with no auth (logs a warning). Local development only. |
| `SESSION_SECRET` | generated | Cookie signing key. If unset, one is generated and stored in `.session_secret` next to the SQLite file (or ephemeral for non-file DBs). Set explicitly for multiple instances. |
| `SESSION_TTL_HOURS` | `12` | |
| `COOKIE_SECURE` | auto | Force `true`/`false`; auto = Secure on https. |
| `CORS_ORIGINS` | `["http://localhost:4000"]` | JSON list of extra allowed origins (e.g. the Vite dev server). Same-host needs nothing. |
| `ENABLE_DOCS` | `false` | Serve Swagger at `/api/docs` (protected only by being unlinked; keep off in prod). |
| `DATABASE_URL` | `sqlite:///./data/superteacher.db` (image: `sqlite:////data/superteacher.db`) | |
| `SCHOOL_TIMEZONE` | `UTC` | IANA zone for school-day defaults and academic cutoffs; see [School calendar](SCHOOL_CALENDAR.md). Cloud Build accepts `_SCHOOL_TIMEZONE`. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_INSIGHT_MODEL` | | AI features; optional. |
| `AI_MAX_CONCURRENT_REQUESTS` | `8` | Shared fail-fast provider budget per server worker across chat, insights and drafts. |
| `AI_CHAT_TIMEOUT_SECONDS` | `90` | Total chat deadline, including tool rounds. |
| `AI_INSIGHT_TIMEOUT_SECONDS`, `AI_PARENT_TIMEOUT_SECONDS` | `45` | Total generation deadlines; cleanup has a separate 5-second cap. |
| `SEED_DEMO_DATA` | `true` | Set `false` in production. |
| `STATIC_DIR` | `web/dist` | |
| `PORT`, `VERSION` | `8080`, `dev` | |

## Docker

```bash
docker build -t superteacher .
docker run -d --name superteacher -p 8080:8080 \
  -e AUTH_PASSWORD="$(openssl rand -base64 24)" \
  -e SESSION_SECRET="$(openssl rand -base64 48)" \
  -e SEED_DEMO_DATA=false -e ANTHROPIC_API_KEY \
  -v superteacher-data:/data superteacher
python deployment_tests.py http://localhost:8080   # export AUTH_PASSWORD first
```

Terminate TLS in front (Caddy, nginx, a load balancer) so the cookie is `Secure`; forward
`X-Forwarded-Proto`. Set `FORWARDED_ALLOW_IPS` to your trusted proxy addresses so Uvicorn uses the forwarded client IP and scheme. Cloud Run configuration sets `*` because connections reach the container through its platform proxy; directly reachable local containers retain Uvicorn's restricted default. The image runs as a non-root user (uid 10001), pins its base images, and its
healthcheck uses the public `/api/health`.

## Cloud Run

The accepted pilot uses SQLite replicated by pinned Litestream to the existing
Cloud Storage bucket. No new paid Cloud SQL instance is needed for this release.
See [current target/configuration evidence and the release sequence](DEPLOYMENT_STATUS.md).
The direct `superteacher` service and custom domains currently serve different releases;
choose the intended service explicitly.

`cloudbuild.yaml` builds and pushes an image tagged with the immutable Cloud Build
ID; it does not deploy or move traffic. The image includes that ID as its default
`VERSION`. A release may also use the full source commit as the image tag and
explicit runtime version. Existing auth/session/AI secrets should be reused by
reviewed version, rather than recreated.

```bash
gcloud builds submit --project=PROJECT --config=cloudbuild.yaml
# Stage only: creates no deployment health-check instance and does not promote traffic.
PROJECT=PROJECT SERVICE=superteacher RUNTIME_SERVICE_ACCOUNT=VERIFIED_ACCOUNT \
  SCHOOL_TIMEZONE=UTC scripts/deploy_cloud_run.sh FULL_SOURCE_COMMIT
```

The script defaults to stage-only: `--no-traffic --no-deploy-health-check`, minimum
zero, maximum one, explicit runtime identity, pinned secret versions, and
`LITESTREAM_REPLICA_URL=gs://PROJECT-superteacher-litestream/SERVICE`. Override
`REPLICA_PREFIX` only deliberately. A candidate using the live prefix must remain
uninvoked until the previous writer has drained; opening a tagged URL can start
another writer. Test a separate staging service with an isolated prefix first.
Cloud Run's default deployment health check also starts a container despite
`--no-traffic`, which is why both flags are required.

Before promotion, preserve a consistent snapshot, rehearse migrations on a copy,
stop new writes, close existing WebSockets, and observe the old writer drain and
final replica sync. Revision maximum-one does not establish single-writer safety
across rollout. The script requires the release operator's explicit precondition;
it does not manufacture drain evidence:

```bash
PROJECT=PROJECT SERVICE=superteacher \
  DRAINED_WRITER_CONFIRMED=yes DRAINED_WRITER_REVISION=OBSERVED_OLD_REVISION \
  scripts/deploy_cloud_run.sh --promote NAMED_CANDIDATE_REVISION
```

Promotion checks the recorded previous revision still receives 100% traffic,
then moves traffic to the named candidate. Verify health, expected version,
protected 401 responses, authenticated workflows and persistence immediately.
It never automatically shifts back after a failed check: drain the candidate
writer and confirm database schema compatibility before rollback. The current
old image knows only migration `0001`; a database upgraded to `0002` needs a
compatible rollback image or a separate recovery replica.

### Durable data on Cloud Run

The image restores its absolute SQLite file before launching the application
under Litestream. Restore errors fail closed. Only this entrypoint's successful
restore path sets `LITESTREAM_RESTORE_VERIFIED=1`; do not set that marker in Cloud
Run environment configuration. Managed SQLite also requires the matching file
and a validated `gs://` replica URL. Local Docker still supports SQLite on a
persistent volume without replication.

The live bucket `portfolio-383615-superteacher-litestream` has versioning, uniform
access, public-access prevention, 7-day soft delete and a 14-day noncurrent-object
lifecycle. Verify these settings and runtime IAM before each release. A wrong
prefix with no replica is treated as first boot: check the exact URI and preserve
existing records before promotion. There is no public-data export in the release
commands.

Replication is asynchronous with a configured 1-second sync interval. Request-
based CPU throttling and hard termination can extend data loss beyond that
interval; it is not a guaranteed one-second RPO. Restore on cold start adds time.
Rehearse restoration into a separate file and synthetic-data persistence across
replacement, and alert on replication failures and backup age. Do not overlap
writers or put the live SQLite database directly on Cloud Storage FUSE.

### Optional PostgreSQL path

PostgreSQL 17 support and focused integration checks remain available. Set
`ST_TEST_POSTGRES_URL` to an isolated test server for `tests/test_postgres.py`.
For a future multi-writer deployment, use the reviewed proposal in
[CLOUD_SQL_PLAN.md](CLOUD_SQL_PLAN.md), provide the instance connection and a
Psycopg database URL secret, and verify/import existing data before a traffic
switch. The build-only YAML neither provisions nor requires Cloud SQL.

## Database migrations (Alembic)

On startup file-based databases run `alembic upgrade head` (in-memory test DBs use `create_all`).
Startup only ever adds/changes schema through migrations and never drops data. A database created
before Alembic is validated against the frozen `0001` schema before stamping and upgrading. Revision `0002` adds database checks for grade levels, score ranges and enum values; invalid existing rows cause an explicit failure before schema changes. Back up first and correct invalid data deliberately.

Creating a revision after editing `superteacher/models.py`:

```bash
alembic revision --autogenerate -m "add parent_email to students"   # DATABASE_URL selects the DB
# review alembic/versions/<id>_*.py (SQLite uses batch mode); expression indexes are not autogenerated
alembic upgrade head
python -m pytest tests/test_migrations.py   # fails if models and migrations drift apart
```

Back up the DB before deploying a release that includes a migration.

## Backups

See [the tested SQLite backup and recovery command](BACKUP_RECOVERY.md) for online snapshots and restore rehearsals into a new file.

* SQLite lives in the `/data` volume. Snapshot the volume, or take a consistent copy with
  `sqlite3 /data/superteacher.db ".backup /backup/superteacher-$(date +%F).db"` (safe while running).
* [Litestream](https://litestream.io) can continuously replicate the DB to GCS/S3
  (`litestream replicate /data/superteacher.db gs://bucket/superteacher`) and restore on a fresh
  container (`litestream restore`); run it as the container entrypoint wrapper or a sidecar.
* Also back up `/data/.session_secret` only if you rely on the generated key (otherwise users just log in again).

## CI

`.github/workflows/ci.yml` runs `ruff check`, `pytest`, the web build, and a Docker job that builds the image,
checks that `/api/health` is up, `/api/overview` is 401, the SPA is served, and that the container refuses
to start without `AUTH_PASSWORD`.
