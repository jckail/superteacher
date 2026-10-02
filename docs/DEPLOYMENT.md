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

```bash
printf '%s' "$(openssl rand -base64 24)" | gcloud secrets create superteacher-auth-password --data-file=-
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create superteacher-session-secret --data-file=-
printf '%s' "$ANTHROPIC_API_KEY"         | gcloud secrets create anthropic-api-key --data-file=-
# grant the service account roles/secretmanager.secretAccessor, then:
gcloud builds submit --config cloudbuild.yaml \
  --project=PROJECT \
  --substitutions=_CLOUD_SQL_INSTANCE=PROJECT:REGION:INSTANCE,_SERVICE_NAME=superteacher
```

`_SERVICE_NAME` defaults to `superteacher`; choose the intended service explicitly for a reviewed live cutover. See [the observed deployment targets and cutover prerequisites](RELEASE_PLAN.md).

`cloudbuild.yaml` uses the immutable build ID as the image tag and `/api/version` value and mounts those secrets as env vars. `--allow-unauthenticated` only means Cloud Run does not
add its own login; the app enforces `AUTH_PASSWORD`. Alternatively drop that flag and use IAP.
Cloud Run deployments require PostgreSQL. The app refuses container-local SQLite when Cloud Run's
`K_SERVICE` environment marker is present. Local Docker deployments continue to support SQLite on a volume.

Before submitting a build, provision a Cloud SQL PostgreSQL database and database user. Store a
SQLAlchemy Psycopg URL in the `superteacher-database-url` Secret Manager secret:

```text
postgresql+psycopg://USER:URL_ENCODED_PASSWORD@/DATABASE?host=/cloudsql/PROJECT:REGION:INSTANCE
```

Provide the actual instance connection name in `_CLOUD_SQL_INSTANCE`. The service account needs
Cloud SQL Client access and permission to read the database URL secret. `cloudbuild.yaml` attaches the
instance and injects `DATABASE_URL`; it does not provision resources or migrate existing SQLite data.
Choose a migration window, back up existing records, and verify imported data before switching traffic.
See [Google's Cloud Run connection guide](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
and [SQLAlchemy's Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg).

CI runs integration checks against an isolated PostgreSQL 17 service. Locally, set
`ST_TEST_POSTGRES_URL` to an isolated test server and run `python -m pytest tests/test_postgres.py`.
These tests create a unique schema and remove only that schema after each test.

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
  (`litestream replicate /data/superteacher.db gcs://bucket/superteacher`) and restore on a fresh
  container (`litestream restore`); run it as the container entrypoint wrapper or a sidecar.
* Also back up `/data/.session_secret` only if you rely on the generated key (otherwise users just log in again).

## CI

`.github/workflows/ci.yml` runs `ruff check`, `pytest`, the web build, and a Docker job that builds the image,
checks that `/api/health` is up, `/api/overview` is 401, the SPA is served, and that the container refuses
to start without `AUTH_PASSWORD`.
