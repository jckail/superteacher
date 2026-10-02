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
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_INSIGHT_MODEL` | | AI features; optional. |
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
`X-Forwarded-Proto`. The image sets `FORWARDED_ALLOW_IPS=*` so uvicorn trusts `X-Forwarded-For`: without it every user appears to come
from the proxy's address and the login lockout becomes global. That is safe when only your proxy can reach the
container, as on Cloud Run; if the container is reachable directly, set it to your proxy's IP. The image runs as a non-root user (uid 10001), pins its base images, and its
healthcheck uses the public `/api/health`.

## Cloud Run

```bash
printf '%s' "$(openssl rand -base64 24)" | gcloud secrets create superteacher-auth-password --data-file=-
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create superteacher-session-secret --data-file=-
printf '%s' "$ANTHROPIC_API_KEY"         | gcloud secrets create anthropic-api-key --data-file=-
# grant the service account roles/secretmanager.secretAccessor, then:
gcloud builds submit --config cloudbuild.yaml
```

`cloudbuild.yaml` mounts those secrets as env vars. `--allow-unauthenticated` only means Cloud Run does not
add its own login; the app enforces `AUTH_PASSWORD`. Alternatively drop that flag and use IAP.
## Durable data on Cloud Run (Litestream → Cloud Storage)

The container filesystem is ephemeral, so the image runs the app under [Litestream](https://litestream.io): it streams
every SQLite change to a Cloud Storage bucket (about 1 s behind), and a new instance restores the database from
that bucket before the app starts. Turn it on by setting `LITESTREAM_REPLICA_URL` (for example
`gcs://BUCKET/superteacher`); without it the app runs as before and data is **not** durable on Cloud Run.

One-time setup (already done for project `portfolio-383615`):

```bash
B=PROJECT-superteacher-litestream
gcloud storage buckets create gs://$B --location us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$B --versioning
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"daysSinceNoncurrentTime":14,"isLive":false}}]}' > lc.json
gcloud storage buckets update gs://$B --lifecycle-file=lc.json
gcloud storage buckets add-iam-policy-binding gs://$B --role=roles/storage.objectAdmin \
  --member=serviceAccount:RUNTIME_SERVICE_ACCOUNT   # bucket-scoped, nothing project-wide
```

Deploy with `PROJECT=... scripts/deploy_cloud_run.sh` (builds, deploys with no traffic, moves traffic, verifies, rolls
back on failure). **Do not** use `gcloud run deploy` with traffic and **do not** open the `--no-traffic` candidate URL
while the old revision is live: two instances writing to one replica fork its history. Keep `--max-instances 1`
(SQLite is a single-writer database).

Behaviour to know:
* **Fail closed.** If the restore fails for any reason other than "no replica yet", the container exits instead of
  starting an empty database. A revision that cannot read the bucket will not go healthy; Cloud Run keeps serving the
  previous one.
* **RPO** is about a second while an instance is running, and a SIGTERM (scale-in or deploy) triggers a final sync.
  A hard crash can lose the last second or two. Restore takes a couple of seconds for a small database.
* **Cold starts** include the restore (`--cpu-boost` is set to shorten them).
* **Rollback** is a traffic shift to the previous revision (`gcloud run services update-traffic SERVICE
  --to-revisions REV=100`); the bucket is untouched by it. Bucket versioning keeps overwritten objects for 14 days.
* **Migrate to Postgres later** (Cloud SQL) when you need more than one instance: see `docs/adr/0001-persistence.md`.
* Drill after any change to this path: write a record, force a new revision
  (`gcloud run services update SERVICE --update-env-vars DRILL=$(date +%s)`), and check the record survived.

## Database migrations (Alembic)

On startup file-based databases run `alembic upgrade head` (in-memory test DBs use `create_all`).
Startup only ever adds/changes schema through migrations and never drops data. A database created
before Alembic (tables, no `alembic_version`) is stamped at the baseline `0001` and then upgraded.

Creating a revision after editing `superteacher/models.py`:

```bash
alembic revision --autogenerate -m "add parent_email to students"   # DATABASE_URL selects the DB
# review alembic/versions/<id>_*.py (SQLite uses batch mode); expression indexes are not autogenerated
alembic upgrade head
python -m pytest tests/test_migrations.py   # fails if models and migrations drift apart
```

Back up the DB before deploying a release that includes a migration.

## Backups

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
