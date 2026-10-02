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

## Accounts mode (passwordless email sign-in)

`AUTH_MODE=accounts` turns Super Teacher into a multi-user **demo**: anyone who gives an email address can sign in and gets
a private, synthetic starter classroom. Default is `AUTH_MODE=passcode` (everything above is unchanged; the passcode maps to
one implicit "owner" user so ownership scoping is uniform). `AUTH_DISABLED` cannot be combined with accounts mode.

Flow: `POST /api/auth/request-link {email}` always answers the same `202` (no user enumeration) and emails a link to
`<PUBLIC_BASE_URL>/auth/verify#token=...`. The token is in the URL **fragment**, so it is never sent to a server, proxy or log, and
a mail scanner that GETs the link cannot burn it. The page `POST`s the token to `/api/auth/verify` (CSRF header + origin check),
which spends it (single use, 15 min), creates the user on first use (with a starter classroom), and starts a **server-side**
session: only the SHA-256 of a 256-bit random id is stored; the cookie (`st_session`, HttpOnly, SameSite=Lax, Secure on https) holds
the id. `POST /api/auth/logout` and `/api/auth/logout-all` revoke sessions immediately. Idle and absolute expiry are enforced.
`DELETE /api/account` (typed email + CSRF header) hard-deletes the user and every owned row; `GET /api/account/export` returns JSON.

Every course, student, score, note, insight, report, CSV, import and AI path (chat context, chat tools, insight cache, parent
drafts) is scoped to the signed-in user. Foreign ids return 404. `/api/metrics` accepts only `METRICS_TOKEN` in accounts mode.

### SendGrid setup

1. Create a SendGrid API key with only the **Mail Send** permission. Verify a sender (single sender or domain authentication) and
   use that address as `AUTH_EMAIL_FROM`. Use a domain you control with SPF/DKIM so links do not land in spam.
2. Put the key in Secret Manager and expose it to the service as `SENDGRID_API_KEY` (never in the image or the repo).
3. Set `AUTH_MODE=accounts`, `AUTH_EMAIL_BACKEND=sendgrid`, `AUTH_EMAIL_FROM`, `PUBLIC_BASE_URL=https://your.domain`
   (the origin used to build links; it is deliberately **not** taken from the Host header) and `SESSION_SECRET`.
4. In SendGrid keep click/open tracking off (the app also asks for that per message): tracking rewrites the link and would
   expose the token to the tracker.
5. The `console` and `file` backends print/store sign-in links, so the app **refuses to start** with them when `K_SERVICE` is set
   (Cloud Run) unless `AUTH_EMAIL_ALLOW_INSECURE_BACKEND=true`. `file` (`AUTH_EMAIL_OUTBOX_DIR`) is for tests and e2e only.

Generate/rotate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SESSION_SECRET, METRICS_TOKEN
```

Rotating `SESSION_SECRET` does not log accounts-mode users out (their sessions are database rows); it only affects the passcode
cookie and the hashing key for stored client-address hashes. To revoke everyone, `DELETE FROM sessions;`. Rotate the SendGrid key by
creating a new one, updating the secret, redeploying, then deleting the old key.

### Abuse and cost controls

Per-address and global request limits are in memory (single instance, matching `maxScale=1`); the per-email limit and token/session
state live in the database. Quotas are per user per UTC day and enforced on the server (chat messages per WebSocket message).
Cache hits and rule-based/template fallbacks (no API key) do not use quota. When exceeded the API answers `429` with a friendly
message and reset time (`detail.code = "quota_exceeded"`; chat sends an error frame with the same fields).

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `AUTH_PASSWORD` | none | **Required** in passcode mode unless `AUTH_DISABLED=true`. Use a long random value. |
| `AUTH_DISABLED` | `false` | `true` runs with no auth (logs a warning). Local development only. |
| `SESSION_SECRET` | generated | Cookie signing key. If unset, one is generated and stored in `.session_secret` next to the SQLite file (or ephemeral for non-file DBs). Set explicitly for multiple instances. |
| `SESSION_TTL_HOURS` | `12` | |
| `COOKIE_SECURE` | auto | Force `true`/`false`; auto = Secure on https. |
| `CORS_ORIGINS` | `["http://localhost:4000"]` | JSON list of extra allowed origins (e.g. the Vite dev server). Same-host needs nothing. |
| `AUTH_MODE` | `passcode` | `passcode` or `accounts` (see above). |
| `PUBLIC_BASE_URL` | first `CORS_ORIGINS` entry | Origin for emailed links, e.g. `https://www.the-super-teacher.com`. |
| `ACCOUNTS_MAX_USERS` | `500` | Sign-up cap. When full, existing users still sign in; new addresses get the same generic reply and no email. |
| `ACCOUNTS_EMAIL_ALLOWLIST_DOMAINS` | empty (anyone) | Comma-separated domains allowed to sign up, e.g. `school.org,example.edu`. |
| `ACCOUNTS_OWNER_EMAIL` | none | The first sign-in with this address adopts all pre-accounts data (the passcode owner's rows). |
| `LOGIN_TOKEN_TTL_MINUTES` | `15` | Lifetime of a sign-in link. |
| `ACCOUNTS_SESSION_IDLE_HOURS` / `ACCOUNTS_SESSION_ABSOLUTE_HOURS` | `72` / `720` | Idle and absolute session lifetime (server-enforced). |
| `ACCOUNTS_LINK_PER_EMAIL_HOUR` / `_PER_IP_HOUR` / `_GLOBAL_HOUR` | `3` / `10` / `300` | Sign-in link requests. Per-email overflow is silent (generic 202); per-address/global answer 429 + `Retry-After`. Address = `request.client` (honours `X-Forwarded-For` only through uvicorn's trusted-proxy setting). |
| `AUTH_EMAIL_BACKEND` | `sendgrid` | `sendgrid`, `console` (redacted log line) or `file` (writes full messages to `AUTH_EMAIL_OUTBOX_DIR`). |
| `AUTH_EMAIL_FROM`, `SENDGRID_API_KEY` | none | Required for `sendgrid`. |
| `AUTH_EMAIL_OUTBOX_DIR` | none | Required for `file`. |
| `AUTH_EMAIL_ALLOW_INSECURE_BACKEND` | `false` | Allow `console`/`file` when `K_SERVICE` is set. Do not. |
| `QUOTA_CHAT_PER_DAY` / `QUOTA_INSIGHT_PER_DAY` / `QUOTA_PARENT_UPDATE_PER_DAY` | `100` / `60` / `20` | Per user per UTC day. |
| `AI_GLOBAL_DAILY_BUDGET` | off | Cap on all metered AI calls per UTC day across users. |
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
/home/jkail/.local/bin/agent-heavy-check -- gcloud builds submit --project=PROJECT --config=cloudbuild.yaml
# Use a fresh isolated prefix after confirming it has no existing writer.
PROJECT=PROJECT SERVICE=superteacher-overhaul-staging \
  REPLICA_PREFIX=overhaul-staging/FRESH_RELEASE_ID ISOLATED_CANDIDATE_CONFIRMED=yes \
  RUNTIME_SERVICE_ACCOUNT=VERIFIED_ACCOUNT SCHOOL_TIMEZONE=UTC \
  /home/jkail/.local/bin/agent-heavy-check -- scripts/deploy_cloud_run.sh FULL_SOURCE_COMMIT
```

The script requires explicit `SERVICE` and `REPLICA_PREFIX`; there is no production
service or storage-prefix default. Only `SERVICE=superteacher-overhaul-staging`
with a nonempty `overhaul-staging/...` prefix and
`ISOLATED_CANDIDATE_CONFIRMED=yes` may stage without drain evidence. That
acknowledgment attests operator verification of **fresh, nonshared storage with no
existing writer**, including the isolated service's own revisions. Being separate
from production is insufficient: reusing an old staging prefix can still fork
writers. The script validates the name/prefix/acknowledgment; it cannot discover
every replica user or prove storage freshness. Confirm those facts before invoking
the helper. Prefixes cannot contain empty or dot segments.

Every other staging operation requires the same observed drain acknowledgment as
promotion. The helper checks the recorded revision against the single revision
at 100% traffic before building, then rechecks immediately before deployment; a
changed revision aborts without deploying. Its `--no-traffic` and
`--no-deploy-health-check`, minimum zero and maximum one avoid the default
deployment health-check startup but do not prevent later invocation from starting
a writer. A tagged URL can launch Litestream restore/replicate before application
startup checks. Those flags and a revision maximum of one never establish a
single-writer handoff.

Before promotion, preserve a consistent snapshot, rehearse migrations on a copy,
stop new writes, close existing WebSockets, and observe the old writer drain and
final replica sync. Revision maximum-one does not establish single-writer safety
across rollout. The script requires the release operator's explicit precondition;
it does not manufacture drain evidence:

```bash
PROJECT=PROJECT SERVICE=superteacher REPLICA_PREFIX=superteacher \
  RUNTIME_SERVICE_ACCOUNT=VERIFIED_ACCOUNT \
  DRAINED_WRITER_CONFIRMED=yes DRAINED_WRITER_REVISION=OBSERVED_OLD_REVISION \
  /home/jkail/.local/bin/agent-heavy-check -- scripts/deploy_cloud_run.sh FULL_SOURCE_COMMIT
# Recheck drain evidence before the separate promotion operation.
PROJECT=PROJECT SERVICE=superteacher REPLICA_PREFIX=superteacher \
  DRAINED_WRITER_CONFIRMED=yes DRAINED_WRITER_REVISION=OBSERVED_OLD_REVISION \
  /home/jkail/.local/bin/agent-heavy-check -- scripts/deploy_cloud_run.sh --promote NAMED_CANDIDATE_REVISION
```

Promotion checks the recorded previous revision still receives 100% traffic,
then privately inspects the candidate revision's environment. Exactly one literal
`LITESTREAM_REPLICA_URL` must equal the explicitly supplied `gs://BUCKET/REPLICA_PREFIX`;
missing, duplicate, referenced or mismatched values abort before traffic changes.
Revision environment values are never printed. It then moves traffic to the named
candidate. Verify health, expected version,
protected 401 responses, authenticated workflows and persistence immediately.
It never automatically shifts back after a failed check: drain the candidate
writer and confirm database schema compatibility before rollback. Verify the
actual deployed migration head against the rollback image; an older schema image
may require a separate recovery replica. In WSL, run the whole helper through
`agent-heavy-check` once, as above; do not nest another wrapper inside it.

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

Revision `0002` (accounts) adds `users`, `sessions`, `login_tokens`, `usage_counters`, `ai_budget` and `courses.owner_id`; existing courses are
backfilled to a deterministic owner user (`owner0000000`, `owner@superteacher.invalid`) so current data keeps working, and the global
`UNIQUE(name)` becomes `UNIQUE(owner_id, lower(name))`. On SQLite this recreates `courses`, so `db.run_migrations` and `alembic/env.py`
switch `PRAGMA foreign_keys` off first (otherwise `DROP TABLE courses` would cascade-delete sections); the revision refuses to run with
foreign keys on. Take a snapshot/backup first. Rollback of the schema fails by design if two owners share a course name; set
`AUTH_MODE=passcode` and redeploy the previous image (extra tables/columns are ignored by it, but it cannot create courses without an owner).

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
