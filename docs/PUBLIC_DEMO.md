# Public synthetic demo

The public classroom opens without a passcode using `PUBLIC_DEMO=true`, `AUTH_MODE=passcode`, and `AUTH_DISABLED=false`. The explicit demo mode retains origin validation and mutation CSRF protection. Current classroom records are synthetic, as confirmed by the owner.

A signed HttpOnly visitor cookie and HMAC network identity share five submitted assistant turns per UTC day. Refresh, reconnect, cancellation and New chat do not refund or reset them. Clearing cookies retains the network allowance. People behind the same public network share its allowance. The UI displays remaining turns and the midnight UTC reset time.

Visitor, network and global counters update atomically before provider work; failed requests count. `AI_GLOBAL_DAILY_BUDGET=50` bounds all public assistant admissions per day. Demo defaults also bound each turn to three model calls and 1,024 output tokens per call. Existing timeouts and concurrency limits apply. These bound work rather than guarantee a currency invoice ceiling. Public insights and parent drafts use deterministic rules/templates.

The pinned `openai-agents==0.23.1` SDK orchestrates actual `Agent`, `Runner.run_streamed` and `FunctionTool` execution. A custom `Model` retains Anthropic transport, Claude Sonnet 5.5, cached system context, signed thinking and owner-scoped tools. SDK tracing and sensitive capture are disabled, with no provider or runner retries. Cancellation drains SDK work before client shutdown and capacity release.

## Verified ingress

Zero `AUTH_FORWARDED_FOR_TRUSTED_HOPS` uses the ASGI client, which Uvicorn may already have rewritten with `FORWARDED_ALLOW_IPS=*`. An isolated Cloud Run runtime probe verified one final platform-appended address after arbitrary supplied prefixes. This release therefore uses `AUTH_FORWARDED_FOR_TRUSTED_HOPS=1`. Exhausted allowances must remain exhausted with new cookies and forged prefixes on both custom domains and run.app during release acceptance. Reverify whenever ingress changes; never infer trust from a platform name.

Additive migration `0005demo` preserves existing classroom tables. Stable session secrets, Litestream and a single writer retain counters across replacements. Qualification covers concurrency, migrations, actual SDK tool streaming, UI, ingress spoofing and replacement persistence.
