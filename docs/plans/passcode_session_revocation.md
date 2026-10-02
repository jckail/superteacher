# Server-revocable passcode sessions

Implementation plan grounded in native HEAD `9a8da6a`, 2026-10-02. Planning
only: no authentication implementation or verification has been performed.

## Problem and outcome

`superteacher/auth.py` issues signed `{v:1}` cookies and authenticates passcode
requests by signature alone. Passcode logout clears the browser cookie but
cannot revoke a copied cookie; its regression remains xfailed in
`tests/test_security_session.py`. Cookies issued in the same second can also be
identical. The WebSocket watcher rechecks that same stateless gate.

Reuse existing `User` and `AuthSession` tables to require both a valid signed
passcode cookie and a live server session. Preserve passcode access to `OWNER_ID`,
current origin/CSRF/proxy checks, cookie name/flags/path, login response shape,
and password/secret rotation behavior. No database migration or new product
endpoint is needed.

## Cookie and database contract

Issue a strict versioned wrapper containing `v:2`, `mode:"passcode"`, and a
256-bit random URL-safe nonce. Keep the current timed serializer and key derived
from `SESSION_SECRET` plus passcode. Validate bounded cookie length, exact payload
shape/types, version, mode, nonce shape, signature, and timed TTL before DB access.
Reject every legacy v1 cookie immediately; users must sign in once after release.
Do not retain stateless fallback or automatically upgrade old cookies.

Store SHA-256 of the **complete signed cookie** in `AuthSession.id_hash`, with
`user_id=OWNER_ID`. Hashing only its decoded nonce would let a cookie holder
submit that nonce to accounts authentication after a mode switch. Also require
accounts cookies to match their generated 43-character URL-safe opaque format;
signed passcode wrappers contain dots and must be refused. Apply that validation
to every accounts-mode session write path too, including revoke/logout and
sign-in verification rotation; rejecting only authentication lookups still lets
a replayed wrapper revoke an opposite-mode session. Shared-database cross-mode
logout and verification must preserve the opposite-mode row. This separates
wire formats without adding a session-mode column.

Extract a small shared row-lifecycle resolver in `superteacher/accounts.py`:
trusted precomputed hash, explicit idle duration, optional required owner ID,
and `touch` flag. It must enforce row existence, absolute/idle expiry, and the
user's disabled flag. Accounts keep their current raw-secret hashing and policy;
passcode resolution requires `OWNER_ID` and returns `is_legacy=True`. Use
conditional row updates/deletes and monotonic `last_seen_at` so a stale read
cannot undo a newer refresh, delete a refreshed session, or raise an ORM stale
write during concurrent logout. Check required ownership before any mutation. Accounts
sessions, including an adopted `OWNER_ID`, remain `is_legacy=False`. Explicit
auth-disabled development retains its owner bypass without issuing sessions.

Use `session_ttl_hours`/`AuthState.ttl` for passcode signature lifetime, DB absolute
expiry, and cookie Max-Age. Never inherit the accounts 720-hour absolute default.
For the bounded first change, use the existing configured
`accounts_session_idle_hours`, capped by passcode absolute TTL, and document
that reuse. Defaults preserve the current 12-hour absolute lifetime. A separate
passcode idle setting can follow as an explicit configuration change.

## Implementation sequence

1. Add strict wire decoders and shared row resolution. Signature validity alone
   must never authenticate a route; preserve low-level signer tests with clear
   naming/documentation.
2. On successful passcode login, ensure the owner exists and atomically delete
   only the presented valid owner's passcode session and insert its replacement.
   Commit before setting the cookie. Current create/revoke helpers commit
   internally, so refactor a transaction-aware primitive or keep rotation in one
   bounded auth transaction. Failed login leaves an existing session untouched.
3. Extend passcode logout to revoke its verified owner's row before clearing the
   cookie. Preserve CSRF/origin checks and idempotent missing-cookie behavior.
   Never delete another account's row from a forged or accounts cookie. Database
   failure must not claim durable revocation or permit signed-only fallback.
4. Resolve REST, `/auth/me`, and WebSockets through the supplied app's
   `session_factory`, never the module-global database. Purge owner rows whose
   database absolute expiry has passed during login, within the rotation
   transaction. Do not apply the passcode idle cap to all owner rows: an adopted
   owner may also have opaque accounts sessions with a longer configured idle
   lifetime, and there is no persisted mode discriminator. The resolver may
   conditionally clean the presented session using its validated mode policy. Do not
   introduce silent session-cap eviction or a passcode logout-all endpoint.
5. Keep `ws_session_active(..., touch=False)` for polling and `touch=True` for
   real user messages. Revocation/expiry closes sockets with 1008 and cancels
   provider work through existing shielded cleanup. Polls/reset frames must not
   extend idle lifetime. Detection occurs on the watcher interval.

Same settings plus the same durable DB must survive restart. The same settings
on a different empty DB must reject the cookie. Secret/password changes, deleted
rows, wrong-owner rows, disabled users, and mode changes fail closed. Rotation
must not change tenant records or legacy-data adoption.

## Focused verification and fixture updates

Remove the copied-cookie logout xfail and add meaningful coverage for:

- Logout rejects a saved cookie while an independent browser remains valid;
  same-second re-login produces a distinct cookie and revokes its predecessor.
- Legacy v1, valid signatures without rows, wrong-owner rows, forged cookies,
  changed secrets/passwords, and cross-mode cookies reject. Test both the full
  passcode wrapper and decoded nonce against accounts mode, including adopted
  owner accounts.
- Same-DB restart succeeds; different-DB replay fails. DB absolute/idle expiry
  and owner disabling reject REST and sockets. Polls preserve idle expiry;
  actual activity refreshes it.
- Missing CSRF/bad Origin cannot revoke; failed login preserves the current row.
  An injected rotation insert failure leaves no partially committed revocation.
  DB failures set no new login cookie and never unlock signed-only access.
- Logout during a blocked fake AI turn cancels it and releases its admission
  permit; cover the real database gate and real chat lifecycle with a fake
  provider, rather than only mocked gate/chat functions. Idle sockets close
  without another message. Existing cancellation,
  trusted-proxy, and forwarded-header spoof tests remain intact.

Enter app lifespan in `tests/test_auth.py`'s foreign-cookie helper: it currently
calls login on `make()` without context/schema initialization. Pure AuthState
secret tests verify signatures, so add shared-DB restart coverage separately.
Tampering tests must not assume three dot-separated cookie components; serializer
compression can introduce a leading dot. Keep signature-clock and DB-clock expiry
checks distinct. Use file-backed SQLite with independent connections for writer
races, rather than concurrent writes through in-memory StaticPool.

Root owns verification: focused auth/security/session/account-mode and WebSocket
checks first, then the final settled CI suite under shared resource limits. Verify
schema/migration history unchanged and update auth/deployment documentation to
state server revocation and the one-time v1 re-login. No cloud release is part of
this implementation plan.
