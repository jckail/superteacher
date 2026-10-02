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
**SQLite on Cloud Run:** the container filesystem is ephemeral. Mount a persistent volume at `/data`
(Cloud Storage FUSE or a Filestore/NFS volume) or use Litestream (below); keep `--max-instances 1`
because SQLite supports a single writer.

## Database migrations (Alembic)

Revision `0002` (accounts) adds `users`, `sessions`, `login_tokens`, `usage_counters`, `ai_budget` and `courses.owner_id`; existing courses are
backfilled to a deterministic owner user (`owner0000000`, `owner@superteacher.invalid`) so current data keeps working, and the global
`UNIQUE(name)` becomes `UNIQUE(owner_id, lower(name))`. On SQLite this recreates `courses`, so `db.run_migrations` and `alembic/env.py`
switch `PRAGMA foreign_keys` off first (otherwise `DROP TABLE courses` would cascade-delete sections); the revision refuses to run with
foreign keys on. Take a snapshot/backup first. Rollback of the schema fails by design if two owners share a course name; set
`AUTH_MODE=passcode` and redeploy the previous image (extra tables/columns are ignored by it, but it cannot create courses without an owner).

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
