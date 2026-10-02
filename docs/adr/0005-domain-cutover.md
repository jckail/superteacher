# ADR 0005: Cutover of www.the-super-teacher.com to the new `superteacher` service

- Status: Proposed, needs owner decision
- Date: 2026-10-02
- Deciders: Jordan Kail (owner)
- Hard prerequisites: ADR 0001 (persistence) must be implemented and drilled first. ADR 0002 (identity) is strongly recommended before more than one person uses it. ADR 0003 (privacy) minimum: privacy notice and no real third-party student data until reviewed.

## Context: how the public site is served today (investigated read-only, 2026-10-02)

All facts below come from `gcloud` read commands (describe, list, logging read), the Cloud Run `domainmappings` REST resource (GET only), `dig`, and plain GETs of public pages. No secret or env var values were read; names only.

### Serving path

```
Browser -> DNS (the-super-teacher.com, www) -> Google Front End (ghs.googlehosted.com / anycast A records)
        -> Cloud Run domain mapping -> Cloud Run service "edutrack" (us-central1, project portfolio-383615)
```

- **Cloud Run domain mappings** (project `portfolio-383615`, region us-central1; `gcloud beta` is not installed here so the same data was read from `domains.cloudrun.com/v1 .../domainmappings`):

  | Domain | routeName (service) | Created | Status |
  |---|---|---|---|
  | `the-super-teacher.com` | `edutrack` | 2024-11-10 | Ready, certificate provisioned (automatic) |
  | `www.the-super-teacher.com` | `edutrack` | 2024-11-10 | Ready, certificate provisioned (automatic) |
  | `jckail.com`, `www.jckail.com`, `jordan-kail.com`, `www.jordan-kail.com` | `quickresume` | 2024-10 | Ready (unrelated site, same project) |

  **Nothing maps to `superteacher`.** The new service is reachable only at its `run.app` URL.
- **DNS** (`dig`, 2026-10-02): `www.the-super-teacher.com` is `CNAME ghs.googlehosted.com.` (TTL 14400 s = 4 h). The apex has four `A` (216.239.32.21, .34.21, .36.21, .38.21) and four `AAAA` records (2001:4860:4802:32::15, :34::15, :36::15, :38::15), TTL 14400. Name servers are `ns-cloud-b1..b4.googledomains.com` (SOA minimum 300 s). There is one `TXT` (a `google-site-verification=` token). No MX records. `gcloud dns managed-zones list` shows **no Cloud DNS zone in project `portfolio-383615`**: the DNS zone is managed outside this project (most likely the registrar's DNS console, formerly Google Domains). **Who can edit DNS must be confirmed by the owner**; I could not read it.
- TLS: certificate for `www.the-super-teacher.com` issued by Google Trust Services (WR3), expires 2026-12-21 (auto-renewed by Cloud Run while the mapping stays).
- Behaviour: `http://the-super-teacher.com/` returns 302 to `https://the-super-teacher.com/`; both apex and `www` serve the app over HTTPS (200). There is no canonical-host redirect between apex and `www`.

### The old `edutrack` service

| Property | Value (source: `gcloud run services/revisions describe`, 2026-10-02) |
|---|---|
| Image | `gcr.io/portfolio-383615/edutrack:v0.1.0` (digest `sha256:099dfa82...`) |
| Revision | `edutrack-00018-t58`, 100% of traffic; 18 revisions total |
| Last deploy | **2024-11-07 12:14 UTC** by Jckail13@gmail.com (gcloud client 498.0.0); service ready since then |
| Scaling | `maxScale=100`, concurrency 80, CPU boost on, 1 vCPU / 512 Mi, timeout 300 s, min instances not set (0) |
| Service account | default compute SA `292025398859-compute@developer.gserviceaccount.com` |
| Env var names | **none** |
| Secret references | **none** (no secret-backed env vars, no volumes) |
| IAM | `allUsers` can invoke (public) |
| Database | **No Cloud SQL instance exists in the project** (`gcloud sql instances list` empty); no env vars or secrets point at Supabase or anything else. Application logs show `backend.app.models.database: Dropped existing tables / Created database tables / Adding sample data / Sample data added successfully` on start-up. **It rebuilds its tables and re-inserts sample data on every container start** (300+ such starts in the last 30 days, the query limit). It is therefore an in-container, ephemeral SQLite-style database holding only generated sample data. The database engine itself is inferred (SQLAlchemy is used; `/api/api/health` reports a SQLAlchemy 2 `text()` error). |
| Image availability | The image is **no longer listed** in the project registry: `gcr.io` is now an Artifact Registry repository created 2026-10-01 holding only `superteacher`; `gcloud container images describe gcr.io/portfolio-383615/edutrack:v0.1.0` returns "not found". Layers may still exist in the legacy bucket `artifacts.portfolio-383615.appspot.com` (2,368 objects, not inspected further). The running revision still serves requests, but a rollback or redeploy of the exact old image cannot be assumed. |

What the public site is: a Vite/React single-page app (bundle `/assets/index-Bl2pR-y0.js`, last-modified 2024-11-07) over a FastAPI backend ("EduTrack", `GET /api/version` returns `{"version":"v0.1.0","git_commit":"development"}`). The OpenAPI schema is public (`/openapi.json`, `/docs`) and shows an **unauthenticated** API: `GET /api/db/classes`, `/api/db/classes/{id}/sections`, `/api/db/classes/{id}/students`, `GET|POST /api/db/students`, `POST /api/db/sections`, `POST /api/db/students/{id}/grades`, plus a health route at the odd path `/api/api/health` that currently returns `{"status":"unhealthy","details":{"database":"Database error: Textual SQL expression 'SELECT 1' should be explicitly declared as text('SELECT 1')",...}}`. `GET /api/health` returns 404. Logs show only light traffic: bots probing `xmlrpc.php`, `zv.php`, `robots.txt`, a handful of real page loads.

### The new service

`superteacher` (revision `superteacher-00002-b5n`, created 2026-10-02 01:50 UTC, image `gcr.io/portfolio-383615/superteacher:c344911`, `maxScale=1`, 1 vCPU / 512 Mi, CPU boost on, public invoker). Env var names: `SEED_DEMO_DATA`, `VERSION`; secret-backed: `AUTH_PASSWORD` (`superteacher-auth-password`), `SESSION_SECRET` (`superteacher-session-secret`), `ANTHROPIC_API_KEY` (`anthropic-api-key`). No volume, **no persistence** (ADR 0001). `GET https://superteacher-292025398859.us-central1.run.app/api/health` returned `{"status":"healthy","database":"ok","ai":true}`; the first request after idle took about 20 s (cold start), then about 0.13 s.

### Surprises worth knowing

1. The public website is **not** Super Teacher; it is the Nov-2024 "EduTrack" demo with fake data and an open write API, still live with a public Swagger UI.
2. There is no production database anywhere to migrate. Nothing real is lost when the old service is retired.
3. The old container image has vanished from the registry, so the old service is effectively not re-deployable.
4. The DNS zone is not in this GCP project; the cutover does not need DNS record changes for the existing hostnames (see below) but the owner must know where DNS lives for any new hostname.
5. `the-super-teacher.com` and `www` both map to the old service, with no apex-to-www redirect.
6. The project also has secrets named `supabase-url`, `supabase-anon-key`, `supabase-service-role` (Terraform-provisioned 2026-07-09); neither Cloud Run service uses them. They appear to belong to the portfolio site.

## Options

### A. Re-point the existing domain mappings (delete and recreate on `superteacher`)

A Cloud Run domain mapping binds one hostname to one service; changing the target means deleting and recreating the mapping (`gcloud beta run domain-mappings delete/create ... --service superteacher`). DNS records stay the same because they point at Google's shared front end, so **no DNS change and no TTL wait** is needed. The cost is a short window (typically seconds to a few minutes, worst case longer while a new managed certificate is issued) during which the hostname returns errors. Acceptable here because the current site has no real users.

### B. Deploy the new image as a new revision of the `edutrack` service

`gcloud run deploy edutrack --image .../superteacher:<tag> ...` swaps the content instantly with no mapping change, and rollback is `update-traffic --to-revisions edutrack-00018-t58=100`. Downsides: the service name lies (`edutrack` serving Super Teacher), the old service's config (maxScale 100, no secrets) must be overwritten to max-instances=1 plus secrets and env (a mistake would let 100 SQLite instances run), and the old revision's image is not guaranteed to restore. Fine as a stop-gap, bad as the end state.

### C. Staging hostname first, then A

Create `app.the-super-teacher.com` (CNAME `ghs.googlehosted.com.`, TTL 300) mapped to `superteacher`, validate end to end on the real domain (cookies, `Secure`, WebSocket, OAuth redirect URIs from ADR 0002), run the pilot there, and only then repoint `www` and apex (Option A). One extra DNS record, zero risk to the current site. **Recommended.**

### D. HTTPS load balancer with a serverless NEG

Lets you switch backends instantly and add Cloud Armor or IAP, but adds a forwarding rule, a static IP and per-GB charges (roughly $18+/month baseline, estimate, verify). Overkill for this stage.

## Cost (monthly, estimates)

| Item | 1 teacher | 10 teachers | 100 teachers |
|---|---|---|---|
| Domain mappings, managed certificates | $0 | $0 | $0 |
| Staging hostname (option C) | $0 | $0 | $0 |
| Cloud Run for the new service | about $0 | about $5 | about $30 (see ADR 0001) |
| Old `edutrack` service | $0 while idle (scale to zero); delete after cutover | | |
| HTTPS LB (option D only) | about $18+ | about $18+ | about $20 to 40 |
| Persistence (ADR 0001) | $0 to 1 (Litestream) or about $28 (Cloud SQL) | | |

## Risks

- **Cutting over before persistence exists** would lose teachers' data at the first scale-to-zero. This is the reason for the go/no-go gate.
- Delete-and-recreate of a mapping can briefly fail certificate issuance; keep the old mapping config recorded so it can be recreated.
- Search engines and any bookmarks hit a login wall instead of the old demo: the old demo has no value, but add a public landing/`robots.txt` decision.
- The cold start (about 20 s) will feel like an outage on first visit; consider `min-instances=1` (extra cost) once there are real users.
- OAuth redirect URIs, `CORS_ORIGINS` and cookie behaviour change with the hostname; the login must be tested on the real domain.
- No canonical redirect between apex and `www` (cookie scope splits, user confusion); add an app-level redirect to one host.
- Cloud Run request timeout is 300 s; chat WebSockets will be cut and must reconnect.
- DNS is controlled outside this project; if the registrar account is not accessible, new hostnames cannot be added.

## Decision needed from the owner

1. Approve Option C (staging host `app.` first) then Option A, or prefer the faster Option B?
2. Where is DNS for `the-super-teacher.com` managed (registrar console) and do you have access? (Not visible from GCP.)
3. Canonical host: `www` (recommended) or apex?
4. What should the old demo become: nothing (retire), or a static landing page before launch?
5. Delete the old `edutrack` service after a cooling-off period (suggest 14 days)? It holds no real data.

## Recommendation

Do not touch the live domain until the go/no-go gate below is green. Then: (1) stand up `app.the-super-teacher.com` on the new service, (2) run the pilot and smoke checks, (3) recreate the `www` mapping on `superteacher`, then the apex with a redirect to `www`, (4) leave `edutrack` scaled to zero for 14 days, then delete it and its mappings' leftovers. No data migration is required; document that the previous site was a sample-data demo.

## Cutover plan

### Go/no-go criteria (all must be true)

1. **Persistence solved and drilled** (ADR 0001): replication or database in place, a row written before a forced new revision and instance deletion survives, restore time measured, alert on failure configured. **No-go if not met.**
2. Identity: either ADR 0002 implemented, or the shared passcode is a strong random secret known only to the owner and only the owner has data in the system (single-user pilot).
3. `SEED_DEMO_DATA=false` in production (already set by `cloudbuild.yaml`; verify on the live revision).
4. Privacy: privacy notice live; prompts do not contain data the owner has not agreed to send (ADR 0003 minimum: owner decision recorded).
5. CI green on the commit being deployed, image built from that commit, tag recorded.
6. Rollback path rehearsed on the staging hostname.
7. Cost and budget alert set on the billing account (billing account "Jordan Kail" is open).
8. Owner has registrar/DNS access for any new hostname.

### Sequence

T-7 days
- Decide ADR 0001/0002; implement; deploy to `superteacher` with `--no-traffic --tag candidate` to get a tagged URL; run smoke checks there.
- Create `app.the-super-teacher.com` CNAME to `ghs.googlehosted.com.` (TTL 300) at the DNS provider; `gcloud beta run domain-mappings create --service superteacher --domain app.the-super-teacher.com --region us-central1`; wait for the certificate (Ready and CertificateProvisioned true).
- Lower TTLs only if you plan to change record values. For the apex and `www` the records do not change, so the existing 14400 s TTL is irrelevant; the repoint happens inside Google.

T-1 day: freeze and validate
- Announce a freeze: no deploys other than the cutover one. Confirm `edutrack` still returns 200.
- Optional archive of the old demo for the record: `GET /openapi.json` and `GET /api/db/classes` (sample data only) saved offline. Not required.
- Record the exact current mapping specs (`routeName: edutrack`, `certificateMode: AUTOMATIC`) so they can be recreated.
- Take a persistence backup/snapshot of the new service's data (empty or pilot data) and confirm it restores.
- Validate on `app.`: login, create course/section/student, add scores, attendance, notes, CSV export, AI chat (WebSocket over `wss`), parent draft, logout; confirm cookies are `Secure; HttpOnly; SameSite=Lax` and host-only.

T-0 (switch, low-traffic window)
1. Note start time. Delete mapping for `www.the-super-teacher.com` (`gcloud beta run domain-mappings delete --domain www.the-super-teacher.com --region us-central1`), immediately create it with `--service superteacher`.
2. Poll `gcloud beta run domain-mappings describe` until Ready and CertificateProvisioned are True; poll `curl -sI https://www.the-super-teacher.com/api/health`.
3. Repeat for the apex, then add the app-level redirect (apex to `www`) in the next release.
4. Update ADR 0002 OAuth redirect URIs and `CORS_ORIGINS` for the final host if not already done in staging.
5. Run the smoke checks below.

Rollback triggers: health not 200 within 15 minutes of the mapping becoming Ready, failed persistence check, login failure, or any data discrepancy.
Rollback steps: delete the new mapping(s) and recreate with `--service edutrack` (the old revision is still serving on its `run.app` URL), which restores the demo site. If the old image is needed (cold start failure of the old revision), there is no copy in the registry; fall back to a static maintenance page service. Keep the new service's data intact; it is not affected by a mapping change.

T+1 to T+14 days
- Watch Cloud Logging for 4xx/5xx, Litestream/database errors, cold-start latencies; confirm daily backup/restore alert.
- After 14 days: scale `edutrack` to zero explicitly (min instances 0 already), remove its public IAM binding, then delete the service. Remove the `app.` staging mapping only if no longer needed.

### Smoke checks (plain HTTP only)

| Check | Expected |
|---|---|
| `curl -sI https://www.the-super-teacher.com/` | 200 and `content-type: text/html`, security headers present (CSP, `X-Frame-Options: DENY`, `nosniff`) |
| `curl -s https://www.the-super-teacher.com/api/health` | `{"status":"healthy","database":"ok","ai":true}` |
| `curl -s .../api/version` | version equals the deployed tag, not `v0.1.0` |
| `curl -s -o /dev/null -w "%{http_code}" .../api/students` (no cookie) | 401 |
| `curl -s -o /dev/null -w "%{http_code}" .../openapi.json` and `/docs` | not the EduTrack schema (404 or the SPA shell) |
| `curl -sI http://www.the-super-teacher.com/` | redirects to https |
| TLS | valid cert, issuer Google Trust Services, SAN includes the host |
| Login in a browser | works, cookie `Secure` |
| WebSocket chat | connects over `wss`, streams a reply, reconnects after 300 s idle |
| Persistence | write a record, force a new revision, record still present |
| Old API gone | `/api/db/classes` returns 401/404, not sample data |
| Logs | no unexpected 5xx; no secrets or prompt text logged |

## Sources and evidence (read 2026-10-02)

- `gcloud run services list|describe edutrack|superteacher`, `gcloud run revisions list|describe`, `gcloud run services get-iam-policy`, `gcloud secrets list` (names), `gcloud sql instances list`, `gcloud dns managed-zones list`, `gcloud artifacts docker images list`, `gcloud logging read` (request paths and log message types only)
- Domain mappings via the Cloud Run `domains.cloudrun.com/v1` REST API (GET only)
- `dig` for A, AAAA, CNAME, NS, TXT, MX, SOA; `curl` GETs of `https://www.the-super-teacher.com/`, `/api/version`, `/api/api/health`, `/openapi.json`, `/docs`, and `https://superteacher-292025398859.us-central1.run.app/api/health`
- Repository `cloudbuild.yaml`, `Dockerfile`, `docs/DEPLOYMENT.md` at origin/main (bb23101)
