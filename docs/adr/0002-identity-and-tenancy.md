# ADR 0002: Identity and tenancy (shared passcode vs per-teacher accounts)

- Status: Accepted (passwordless-email variant). Implemented on branch `team/accounts`; see "What was built" below.
- Date: 2026-10-02
- Deciders: Jordan Kail (owner)
- Depends on: ADR 0001 (where user rows live). Informs: ADR 0003 (who is accountable for which student record), ADR 0005.

## Accepted variant and historical baseline

The accepted passwordless-email variant is described under "What was built" below.
The original shared-passcode baseline and provider comparisons preserve the
reasoning behind that decision. They do not describe the current account schema:
current source has user rows, owner-scoped courses and revocable account sessions.
Google sign-in and Clerk alternatives were not adopted as written.

Use [current configuration](../DEPLOYMENT.md), [local account administration](../ACCOUNT_ADMIN.md)
and the [operator runbook](../OPERATOR_RUNBOOK.md) for current interfaces and
ownership. The release owner's [deployment ledger](../DEPLOYMENT_STATUS.md) qualifies
serving mode, owner adoption and actual sign-in delivery separately; the accepted
design and implemented source do not establish those operational outcomes.

## Historical shared-passcode baseline

Current model (`superteacher/auth.py`, `docs/DEPLOYMENT.md`): one shared passcode (`AUTH_PASSWORD`, from Secret Manager secret
`superteacher-auth-password`) signs an `st_session` cookie (itsdangerous, 12 h TTL, key derived from `SESSION_SECRET` plus the passcode). There
is no user table. Whoever holds the passcode sees **every** course, student, note and AI conversation in the database. Login throttling
is in process memory, so it only holds for one instance.

Data model (`superteacher/models.py`): `Course 1-* Section 1-* Student ...`. There is **no owner column anywhere**, and
`courses.name` is globally `UNIQUE`, so two teachers cannot both have a course called "Algebra 1". Every query (`queries.load_students`,
roster routers, reports, AI tool handlers in `ai_tools.py`, the chat roster snapshot in `ai.build_context_parts`) reads all rows.
The AI chat and its tools therefore also see every student in the system.

This is acceptable for one teacher (the owner) and not acceptable for a second teacher, because a second teacher would see the first
teacher's students and the AI would mix them. It is also not acceptable for a school pilot: a shared secret cannot be revoked per
person, has no audit trail ("who changed this grade"), and a departing teacher keeps access.

Platform facts (project `portfolio-383615`, read 2026-10-02): the `superteacher` Cloud Run service allows `allUsers` to invoke (the app is
the gatekeeper), ingress `all`, `maxScale=1`. No identity provider is configured yet.

## What was built (passwordless-email variant, accepted)

The owner chose a public demo ("anyone who gives an email address") with synthetic data only, so none of options A to D was adopted
as written: it is a self-managed **passwordless email sign-in** (a reduced option A: no passwords, no TOTP, no recovery flows), with
server-side revocable sessions instead of the stateless cookie.

- `AUTH_MODE=passcode|accounts` (default `passcode`, unchanged behaviour; the passcode maps to an implicit owner user).
- Tables: `users`, `sessions` (SHA-256 of a 256-bit id, idle + absolute expiry, revocable), `login_tokens` (hashed, 15 min, single use),
  `usage_counters`, `ai_budget`; `courses.owner_id` with `UNIQUE(owner_id, lower(name))`. The original accounts branch used migration `0002`; current native accounts migration is `0003`, following integrity `0002`, and backfills existing rows to the owner user. An original accounts-`0002` snapshot requires the [offline adoption procedure](../IDENTITY_INTEGRATION.md); do not change its stamp or start native migrations against it.
- Links open an SPA page with the token in the URL fragment, which POSTs it (scanner-safe, CSRF + origin checked). Generic `202` replies,
  per-address/per-email/global rate limits, `ACCOUNTS_MAX_USERS`, optional domain allowlist. SendGrid over httpx; `console`/`file`
  backends refused in production.
- Tenancy: one dependency, `auth.current_user`, threaded through every router, `queries.py` (`owner_id` is a required argument), `reports.py`,
  and every AI path (chat roster snapshot, tools, insight cache, parent drafts, WebSocket). Foreign ids are 404. Tests: `tests/test_accounts_tenancy.py`
  and a route-inventory test that fails if an authenticated route does not resolve `current_user`.
- Account endpoints: `GET /api/account/export`, `DELETE /api/account` (typed email), `POST /api/auth/logout-all`.
- Per-user daily quotas and an optional global AI budget; a synthetic starter classroom on first sign-in.

Differences from the proposal above: no Google/Clerk, no `provider`/`provider_sub`/`name` columns (email is the identity), the owner email for
adoption is optional config (`ACCOUNTS_OWNER_EMAIL`) rather than a refusal to migrate, `owner_id` is backfilled in the same revision (not a second one),
the throttle for sign-in links is partly in memory (single instance) and partly in the database. Not built: organisations/roles, Postgres RLS,
MFA, an operator console to disable users (set `users.disabled=1` in the database; takes effect on the next request).

## Options

### A. Self-managed email + password + TOTP

Own `users` table, Argon2id hashes, TOTP (pyotp), recovery codes, email verification and password reset (needs an email sender; the project has a
`sendgrid-api-key` and `smtp-password` secret by name), lockout and breach-password checks.

Pros: no vendor, no per-user cost, full control of cookies.
Cons: we own every security-sensitive flow for children's records: reset emails, enumeration, credential stuffing, MFA recovery, support burden. Estimated 8 to 12 days with tests and a security review. Highest long-term risk per unit of value. Not recommended.

### B. Google sign-in (OpenID Connect, "Sign in with Google") with our own session cookie

Authorization-code flow with PKCE, verify the ID token (`iss`, `aud`, `exp`, `email_verified`, `sub`), upsert a `users` row keyed by Google `sub`, issue the existing signed cookie containing `user_id`. Libraries: Authlib or `google-auth`. Scopes `openid email profile` are non-sensitive, so no Google verification review is needed
once the OAuth consent screen is "In production" (external). Access control: an allowlist table of approved emails (invite-only), later a Workspace domain (`hd` claim) rule per school.

Pros: teachers already have Google accounts (most US districts are Google Workspace for Education); MFA, phishing protection and account recovery are Google's problem; no passwords stored; no per-user fee; works unchanged across multiple Cloud Run instances because the session cookie is stateless and signed.
Cons: some district Workspace admins block third-party OAuth apps until an admin approves the client ID (a sales/onboarding step, not an engineering one); teachers on Microsoft 365 or Apple-only schools cannot sign in (add Microsoft later, or fall back to magic link); we still own session handling and CSRF (already implemented). Estimated 3 to 5 days including the tenancy work in the next section is separate (below).

### C. Clerk

Hosted users, organisations and sessions. The owner already has Clerk tooling (Clerk skills are installed in this workspace, so the integration pattern is familiar). Backend verifies Clerk session JWTs
(JWKS) in `auth.require_auth`; the React app uses `@clerk/clerk-react`. Pricing (secondary summaries, 2026-10-02, verify at clerk.com/pricing): Free up to 10,000 MAU and 100 monthly active organisations; Pro $25/month plus about $0.02/MAU above 10,000, extra organisations about $1 each.

Pros: social + email + MFA + organisations/roles (school tier) + invitations + admin UI with little code; fastest route to the org tier; webhooks to sync users.
Cons: another processor holding teacher PII (email, name), not student data, but it sits in the login path for a children's-data app, so it needs a vendor DPA review (ADR 0003); vendor lock-in of user ids (mitigate by storing our own `users.id` and mapping `clerk_user_id`); the SPA must load a third-party script, which loosens the strict CSP in `main.py` (`script-src 'self'`, `connect-src 'self'`); outage in Clerk is an outage for login. Estimated 3 to 4 days for teacher login; org features are cheaper here than in B.

### D. Cloud IAP or Identity Platform

- IAP direct on Cloud Run (`--iap`, no load balancer, no extra charge; Google docs, read 2026-10-02): puts a Google login in front of the service. Access is granted by IAM members (individual Google accounts or groups). Good for a closed circle of known Google accounts; poor for onboarding strangers (each teacher needs an IAM binding added by an admin) and it hides the app from health probes and public pages unless carefully excluded. It also sets `X-Goog-Authenticated-User-Email`/JWT headers that the app would trust.
- Identity Platform (Firebase Auth under GCP): hosted sign-in for Google, email/password, SAML/OIDC, TOTP MFA (no extra cost per Google's pricing page summary, SMS MFA is per message), a free MAU tier then per MAU. Pros: same cloud, SAML for districts. Cons: Firebase SDK in the SPA (CSP changes similar to Clerk), more console configuration, weaker org features than Clerk.

Neither adds data-scoping; the tenancy work below is identical for all options.

## Data scoping model

Regardless of the login option:

1. **`users`**: `id` (12-char hex like other ids), `email` (unique, lowercase), `provider`, `provider_sub`, `name`, `created_at`, `disabled_at`.
2. **`courses.owner_id`** FK to `users.id` (NOT NULL after backfill), index. `students`, `sections`, `assessments`, `scores`, `attendance`, `notes`, `insights` inherit ownership through `section -> course`, so no column is needed on them but every query must join through the owner. Replace `UNIQUE(name)` with `UNIQUE(owner_id, name)` (Alembic batch operation on SQLite, ordinary `ALTER` on Postgres).
3. **Single choke point**: replace `Depends(get_db)` in routers with a `ScopedSession` carrying `current_user`, and make `queries.load_students`, `get_student_or_404`, the AI tool handlers (`execute(db, ...)` in `ai_tools.py`), `ai.build_context_parts` and report/CSV builders take an `owner_id`. A cross-tenant test (user A creates data, user B gets 404 on every endpoint, WebSocket chat and tool call) is the main acceptance test.
4. **Organisation tier (later)**: `organisations` and `memberships(user_id, org_id, role in {owner, admin, teacher})`; `courses.org_id` optional, ownership becomes "teacher member of the course's org". Roles: school admin can see rosters and usage but not necessarily notes. Needed for school contracts, co-teaching, and a data-protection contact per school. Keep `owner_id` as the creator so teachers can leave and take nothing. Clerk (option C) provides most of this out of the box; with B it is a new table and an invite flow (about 4 to 6 extra days).
5. **Postgres row-level security** (after ADR 0001 option b): `SET LOCAL app.user_id` per request plus RLS policies on courses as a defence-in-depth backstop against a missed filter. Not available on SQLite.

Existing data: the current database belongs to the owner. Migration `0003_users_and_ownership` creates a `users` row for the owner's email, sets `courses.owner_id` for all existing courses, then adds NOT NULL.

## Session handling on Cloud Run

- Keep stateless signed cookies (already `HttpOnly`, `SameSite=Lax`, `Secure` on https). Put `user_id` and a `session_version` in the payload; store `session_version` on the user row so "sign out everywhere" and offboarding revoke immediately (one cheap row read per request).
- `SESSION_SECRET` must be the same on all instances: it already comes from Secret Manager (`superteacher-session-secret`). Today the key also mixes in the passcode; drop that when the passcode goes away. Provide key rotation by accepting two keys.
- Login throttling currently lives in process memory (`auth.py`). Under Google/Clerk sign-in the throttle is no longer the main defence. If `max-instances` rises above 1 after ADR 0001 (b), move any remaining counters to the database.
- Custom domain: the OAuth redirect URIs and cookie host must match `https://www.the-super-teacher.com` after cutover (ADR 0005). Register both the `run.app` URL (for testing) and the custom domain, and keep cookies host-only (no `Domain` attribute).
- Behind Cloud Run's proxy, `X-Forwarded-Proto` is already honoured (`FORWARDED_ALLOW_IPS=*`).
- WebSocket chat authenticates from the same cookie; Cloud Run caps requests at the service timeout (currently 300 s), so the client must reconnect; the new session check applies on every connect.

## Cost (monthly, estimates)

| Option | 1 teacher | 10 teachers | 100 teachers | Notes |
|---|---|---|---|---|
| A self-managed | $0 + email sending (SendGrid free tier about 100/day) | $0 | $0 to 20 | engineering time dominates |
| B Google sign-in | $0 | $0 | $0 | no per-user fee |
| C Clerk | $0 (free tier) | $0 | $0 (under 10k MAU; orgs: 100 free, then about $1 each) | Pro $25 if you need Pro-only features |
| D1 IAP | $0 | $0 | $0 | needs per-user IAM bindings, so operational time grows |
| D2 Identity Platform | $0 | $0 | $0 | free MAU tier; SMS MFA extra |

Engineering effort (estimates, one engineer who knows the codebase): B plus tenancy 5 to 8 days; C plus tenancy 4 to 7 days; A plus tenancy 10 to 15 days; tenancy alone is 2 to 4 of those days (including the cross-tenant test suite and migration).

## Risks

- Tenancy filters missed in one query path (most likely in AI tools and report builders, which read through `load_students`). Mitigate with the single choke point and a test that iterates every registered route.
- Backfill picks the wrong owner for existing data. The migration must be explicit about the email and refuse to run without it.
- District Workspace admins block the OAuth client (B). Have a magic-link fallback or Clerk ready.
- Account takeover of a teacher's Google account exposes all their students: require MFA at the provider (Google enforces for Workspace admins; Clerk lets us require it).
- Orphaned accounts: define an offboarding path (disable user, reassign or export courses). Ties to deletion obligations in ADR 0003.
- Passcode retained "just in case" becomes a permanent backdoor. Remove it after the first sign-in is confirmed.

## Historical decision questions (accepted email variant recorded above)

1. Provider: Google sign-in only, Clerk, or other?
2. Is the first real use "owner plus a few invited teachers" (invite allowlist, no org tier) or "a school" (org tier now)?
3. Existing data: confirm which email owns the current courses.
4. Should the shared passcode remain as a break-glass admin path for a defined period?

## Recommendation

**Option B (Google sign-in) with an invite-only email allowlist, plus `owner_id` on courses**, no organisation tier yet. It unblocks real
use by more than one teacher in roughly 5 to 8 days, costs nothing, adds no new data processor, and keeps the strict CSP. Design the
`users` table and `owner_id` so an `organisations` layer can be added later without rewriting queries. Choose **Clerk (C)** instead if you
expect to sell to schools within a quarter and want organisations, roles and invitations without building them; its free tier covers 10,000 MAU. Do not build option A; do not use IAP as the product login.

Minimal path that unblocks real use:
1. Migration: `users`, `courses.owner_id`, `UNIQUE(owner_id, name)`, backfill to the owner.
2. Google OIDC login routes and allowlist; session carries `user_id`.
3. Owner-scoped queries via one choke point, AI tools and chat context included; cross-tenant tests.
4. Frontend: replace the passcode form with "Sign in with Google"; show the signed-in email; logout.
5. Remove or disable `AUTH_PASSWORD` once the owner has signed in.

## Migration and rollback plan

- Ship behind a flag `AUTH_MODE=passcode|google` (default `passcode`) so deploys can precede the switch.
- Take a Litestream snapshot or Cloud SQL backup (ADR 0001) before running the ownership migration; the migration is additive (nullable `owner_id`, backfill, then NOT NULL in a second revision) so the previous image still runs against the intermediate schema.
- Rollback: set `AUTH_MODE=passcode` and redeploy the previous image; the extra columns are ignored by old code. If the uniqueness change must be reversed, the old `UNIQUE(name)` can only be restored when no two owners share a course name (check first).

## Sources (read 2026-10-02)

- Enable IAP for Cloud Run, https://docs.cloud.google.com/iap/docs/enabling-cloud-run
- Identity Platform pricing, https://cloud.google.com/identity-platform/pricing (via summary; verify)
- Clerk pricing summaries (WorkOS, costbench and others, 2026); verify at https://clerk.com/pricing
- Repository: `superteacher/auth.py`, `models.py`, `queries.py`, `ai_tools.py`, `ai.py`, `docs/DEPLOYMENT.md` at origin/main (commit bb23101)
