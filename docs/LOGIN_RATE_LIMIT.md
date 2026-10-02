# Proxy identity for sign-in limits

[Issue #30 / F-05](https://github.com/jckail/superteacher/issues/30) concerns rotating
caller-supplied `X-Forwarded-For` prefixes. With Uvicorn wildcard proxy trust, the
rewritten `request.client` can select an unverified prefix. A new address per request
then evades per-client passcode/link/verification counters. The passcode global
limiter still limits guesses, but can also lock out other users.

## Explicit trusted-suffix policy

`AUTH_FORWARDED_FOR_TRUSTED_HOPS` defaults to `0`, preserving `request.client` identity
and existing Uvicorn trust behavior. Local/direct containers should retain restricted
Uvicorn proxy trust. **The default does not repair wildcard trust by itself.**

A positive value (1–8) selects the leftmost address within that many verified,
proxy-appended addresses at the right end of one `X-Forwarded-For` field. For a
verified single-appended-client profile, `1` selects the rightmost address. For a
verified two-address suffix `client, proxy`, `2` selects the client. Caller-supplied
prefix values are ignored, even if they contain arbitrary text. All selected suffix
addresses must parse as IPs. IPv6 is canonicalized; IPv4-mapped IPv6 shares the IPv4
counter. Bracket/port notation and IPv6 scope IDs are refused.

The selected identity is used consistently for passcode attempts, sign-in link
requests/token IP hashes and sign-in token verification. It is a limiter key, not
an authenticated identity. This policy does not rewrite ASGI `client`, scheme, host
or origin, alter cookies, bypass CSRF or replace Uvicorn trusted-proxy configuration.

Missing, duplicate, oversized (>4096 characters), too-short or malformed trusted
headers share one `unverified-forwarded-client` bucket. There is no fallback to a
possibly spoofed `request.client`. An unexpected header profile can therefore cause
shared throttling; inspect ingress configuration rather than weakening the fallback.

## Release-owner verification before enabling

This is source support with synthetic tests, **not a verified production hop count**.
No deployment/environment changes are included. The release owner must establish:

1. Every route to this container passes through the intended trusted ingress, including
   alternate service URLs. Direct access with caller-controlled headers is excluded.
2. The ingress appends or replaces a fixed trusted suffix after unverified values;
   observed IPv4/IPv6 requests and duplicate-header handling match that contract.
3. The configured count never reaches into a caller-supplied prefix. Additional
   proxy hops and ingress changes require a new review; a guessed larger count is unsafe.
4. Synthetic rotating-prefix attempts share a counter, while different verified
   clients receive distinct counters. Missing/malformed headers share the fixed bucket.
5. Passcode, request-link and verify limits, global caps, CSRF and secure-cookie
   behavior still meet the exact serving artifact's acceptance gates.

Do not infer a count solely from `K_SERVICE` or the name “Cloud Run.” Google's
[external Application Load Balancer documentation](https://docs.cloud.google.com/load-balancing/docs/https#x-forwarded-for_header)
describes an appended `client, load-balancer` pair and warns that preceding values
are unverified; downstream reverse proxies may add more addresses. That document
does not establish this deployment's complete Cloud Run path.
[Uvicorn's settings](https://www.uvicorn.org/settings/#http) document wildcard trust,
and its [deployment guidance](https://www.uvicorn.org/deployment/#running-behind-nginx)
notes that more complex proxy configurations can need additional handling.

Edge rate limiting/Cloud Armor can complement the app counters, subject to the
release owner's ingress plan. The counters remain in-process and are not a distributed
abuse ledger. Shared NATs, distributed attacks, global lockout and provider costs need
separate controls. Keep #30 open until the actual ingress policy is verified, configured
and accepted; do not represent these offline checks as live deployment hardening.

## Focused reproduction

```sh
python -m pytest tests/test_forwarded_limits.py tests/test_auth.py tests/test_accounts_limits.py -q
```

These tests use synthetic addresses, in-memory databases, file email and the actual
Uvicorn wildcard proxy middleware. They make no provider or cloud requests. Their
fixed appended suffix models an explicitly verified policy; it is not a measurement
of a platform's current headers.
