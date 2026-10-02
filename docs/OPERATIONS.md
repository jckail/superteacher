# Operations

Everything here is implemented in `superteacher/observability.py` (installed by one `observability.install(app)` call
in `create_app`). The design rule: **logs and metrics never contain student data**. They are built only from the HTTP
method, the matched route *template*, the status code, timings and a validated request id. No query strings, headers,
cookies, bodies, names, notes, scores or passcodes are ever read. A redacting formatter is a second line of defence
for free-form messages logged elsewhere.

## Liveness vs readiness

| Endpoint | Auth | Meaning | Failure |
| --- | --- | --- | --- |
| `GET /api/health` | public | Process is up and can run `SELECT 1`. Use for liveness / container HEALTHCHECK. | `{"status":"unhealthy"}` (HTTP 200, legacy shape) |
| `GET /api/ready` | public | Safe to receive traffic: DB reachable **and** Alembic revision equals the code's head. | HTTP **503**, body below |

```json
{"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}
{"status": "not_ready", "checks": {"database": "ok", "migrations": "behind"}}
{"status": "not_ready", "checks": {"database": "error", "migrations": "unknown"}}
```

Check values are fixed strings; exception text, hosts, revision ids and paths never appear in the response (the
exception *type* is logged server-side). `migrations` is `n/a` for in-memory SQLite (tests), which uses `create_all`.
Do not point a liveness probe at `/api/ready`: a DB blip would restart healthy containers. Use it for startup/readiness
checks and uptime monitoring.

## Request ids

* Inbound `X-Request-ID` is accepted if it matches `[A-Za-z0-9][A-Za-z0-9._-]{7,63}` (8-64 chars, no whitespace,
  CR/LF or non-ASCII); otherwise a fresh 32-char hex id is generated and the inbound value is discarded.
* The id is echoed in the `X-Request-ID` response header (also on the WebSocket handshake) and is attached to every log
  record emitted while the request is in flight (contextvar `observability.request_id_var`).
* The middleware is pure ASGI (not `BaseHTTPMiddleware`), so WebSockets and streaming are unaffected.

## Log schema

One JSON object per line on stderr (Cloud Run forwards it to Cloud Logging; `severity` is the field Cloud Logging
reads).

Common fields: `ts` (ISO-8601 UTC, ms), `level`, `severity`, `logger`, `request_id` (null outside a request).

| `event` | Extra fields | Level |
| --- | --- | --- |
| `http_request` | `method`, `route` (template, e.g. `/api/students/{student_id}`, or `unmatched`), `status`, `duration_ms` | INFO; ERROR for 5xx; DEBUG for `/api/health`, `/api/ready`, `/api/metrics` (probe noise) |
| `ws_open` | `route` | INFO |
| `ws_close` | `route`, `accepted`, `close_code`, `duration_ms` | INFO |
| `ai_call` | `kind`, `outcome`, `seconds` | INFO |
| (none: free-form app logs) | `msg`, and `exc_type` + redacted/truncated `exc` when an exception is attached | as logged |

Not logged, by construction: client IP, query string, headers, cookies, request/response bodies.

Redaction (applied to all free-form text): `Bearer`/`Basic` credentials, `key=value` / `"key": "value"` pairs for
authorization, cookie, api key, passcode, password, secret, token, session, csrf; `sk-...` API keys; any `?query`;
opaque tokens of 40+ characters; and the exact configured `AUTH_PASSWORD`, `ANTHROPIC_API_KEY`, `SESSION_SECRET` and
`METRICS_TOKEN` values wherever they occur. Values are truncated at 1000 chars (tracebacks at 4000).

uvicorn's own access log is disabled by `install()` because it prints the raw path **and query string**; the
`http_request` event replaces it. (Third-party loggers such as `httpx` log outbound URLs at INFO; none carry student
data today. Re-check if you add an integration.)

## Metrics

`GET /api/metrics`, Prometheus text format 0.0.4. In-process, per instance (Cloud Run scales to several instances;
aggregate in the scraper and expect counters to reset on restart/new revision).

| Metric | Type | Labels |
| --- | --- | --- |
| `st_http_requests_total` | counter | `method`, `route` (template), `status_class` (`2xx`...) |
| `st_http_request_duration_seconds` | histogram | `route` |
| `st_login_failures_total` | counter | none (401 on `POST /api/auth/login`) |
| `st_login_lockouts_total` | counter | none (429 on the same route) |
| `st_ai_calls_total` | counter | `kind` (`chat`/`insight`/`parent_update`), `outcome` (`ok`/`error`/`timeout`/`fallback`) |
| `st_ai_call_seconds` | histogram | `kind` |
| `st_websocket_connections_open` | gauge | none |
| `st_websocket_connections_total` | counter | `outcome` (`accepted`/`rejected`) |
| `st_websocket_duration_seconds` | histogram | none |
| `st_metrics_dropped_series_total` | counter | none |

Cardinality is bounded: only route templates are used (unknown paths are `unmatched`, methods outside the standard set
are `OTHER`), at most 300 distinct route labels (then `other`) and 1000 series per metric.

AI outcome notes: `insight` and `parent_update` swallow upstream errors and fall back to rules/templates, so those
failures are recorded as `fallback` (the real error is in the logs). `chat` raises, so it records `error`/`timeout`.
Cache hits and unconfigured AI (no `ANTHROPIC_API_KEY`) are not recorded; a client disconnect mid-stream is not an AI
outcome.

### Scraping (it is protected)

`/api/metrics` returns 401 without credentials. Two options:

1. **Bearer token (recommended for scrapers).** Set `METRICS_TOKEN` (store it in Secret Manager and mount it as an env
   var like `AUTH_PASSWORD`). The scraper sends `Authorization: Bearer <token>`. The token unlocks *only* this endpoint.
   The token is compared in constant time and is redacted from logs.
2. **Session cookie.** `POST /api/auth/login` with the passcode, then send the `st_session` cookie. Fine for ad-hoc
   `curl`, awkward for a scraper because sessions expire.

With `AUTH_DISABLED=true` (local dev) it is open, like every other route.

Google Managed Service for Prometheus / an OTel sidecar can scrape with a bearer token; if you cannot add headers,
use Cloud Logging log-based metrics on the `http_request`/`ai_call` events instead (see below).

## Cloud Run

Service `superteacher`, region `us-central1` (see `cloudbuild.yaml`). Every deploy creates an immutable revision.

```bash
gcloud run revisions list --service superteacher --region us-central1
# Roll back instantly (no rebuild): send 100% of traffic to a known-good revision
gcloud run services update-traffic superteacher --region us-central1 --to-revisions REVISION_NAME=100
# Canary: 10% to the new revision
gcloud run services update-traffic superteacher --region us-central1 --to-revisions NEW=10,OLD=90
# Return to "latest revision gets everything"
gcloud run services update-traffic superteacher --region us-central1 --to-latest
```

Migrations run at startup (`run_migrations`) and are additive. An older image started against a newer database reports
`migrations: behind` on `/api/ready` (503), so a rollback across a schema change shows up as not-ready: keep the rollback
window short or roll forward.
Configure the startup probe on `/api/ready` and liveness on `/api/health`:

```bash
gcloud run services update superteacher --region us-central1 \
  --startup-probe httpGet.path=/api/ready,periodSeconds=5,failureThreshold=24 \
  --liveness-probe httpGet.path=/api/health,periodSeconds=30
```

### Cloud Logging queries

Trace one request (paste the id the user reported; Cloud Run puts our JSON in `jsonPayload`):

```
resource.type="cloud_run_revision"
resource.labels.service_name="superteacher"
jsonPayload.request_id="REQUEST_ID"
```

Useful filters:

```
jsonPayload.event="http_request" AND jsonPayload.status>=500
jsonPayload.event="http_request" AND jsonPayload.route="/api/auth/login" AND jsonPayload.status=401
jsonPayload.event="http_request" AND jsonPayload.duration_ms>2000
jsonPayload.event="ai_call" AND jsonPayload.outcome=("error" OR "timeout")
jsonPayload.event="ws_close" AND jsonPayload.accepted=false
```

### Suggested alert policies

Create log-based metrics from the filters above (or use the Prometheus metrics if scraped).

| Alert | Condition | Notes |
| --- | --- | --- |
| Service down | Uptime check on `/api/ready` fails for 2 consecutive minutes | public, no auth needed |
| 5xx rate | `status>=500` > 2% of requests over 5 min (min 20 requests) | page |
| Latency | p95 `duration_ms` > 2 s over 10 min on non-AI routes | ticket |
| Login brute force | `POST /api/auth/login` 401 > 20 in 5 min, or any 429 burst | possible guessing; check the throttle |
| AI degradation | `ai_call` outcome in (`error`,`timeout`,`fallback`) > 30% over 15 min (min 10 calls) | users still get rule-based output; ticket |
| Not ready after deploy | `/api/ready` 503 on a serving revision | roll back with `update-traffic` |
| Instance churn | container restarts > 3 in 15 min (Cloud Run system metric) | OOM / crash loop |

## Correlating a user-reported failure to a request id

1. Every API response carries `X-Request-ID`. Today a user can read it in browser devtools (Network tab, response
   headers) or you can ask for the time and route and filter `jsonPayload.route=... AND status>=400` around that time.
2. Search Cloud Logging for `jsonPayload.request_id="<id>"`: you get the `http_request` line (route template, status,
   duration) plus any warnings/errors logged during that request, all sharing the id.
3. The frontend cannot show the id yet. Suggested one-line client change (not applied here; `web/src` is owned by other
   work): in the API helper that throws on `!res.ok`, include the header in the error, e.g.
   `throw Object.assign(new Error(msg), { requestId: res.headers.get('x-request-id') })`, and render
   `Ref: ${err.requestId}` in the toast/error boundary so users can quote it. For the chat WebSocket the handshake
   response carries the same header, but browsers do not expose WebSocket handshake headers; have the server include the
   id in the `error` event if you need it there.
