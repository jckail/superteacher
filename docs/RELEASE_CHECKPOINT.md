# Historical release checkpoint (2026-10-02)

This file preserves the earlier release session's observations, incidents and owner decisions,
including source `89c0071` and serving revision `superteacher-00008-96g` recorded below.
These observations describe that checkpoint; they do not establish the currently serving revision
or acceptance of a later source, build or candidate.

For the latest verified source, immutable build and candidate acceptance evidence, start with
[Deployment status and execution handoff](DEPLOYMENT_STATUS.md). Use the
[operator runbook](OPERATOR_RUNBOOK.md) for deploy, rollback, restore and incident procedures.
The existing release owner verifies live service state and outstanding gates before execution.

## Observed

**Code.** `main` (`89c0071`) contains PRs #1 to #16: overhaul, hygiene, observability, decision records, security review and
patches, E2E and accessibility suite, Litestream persistence, scale work, accounts, the release team's large overhaul
(#15) and sign-in email resilience (#16). CI on the merged PRs passed.

**Production service** `superteacher` (project `portfolio-383615`, `us-central1`):

| Item | State |
|---|---|
| Serving revision | `superteacher-00008-96g`, image built from `dae26a5` (before #15), passcode mode |
| Persistence | Litestream to `gs://portfolio-383615-superteacher-litestream/superteacher`; **drill passed** (a record survived a forced new revision with an empty disk) |
| Accounts | **off** (`AUTH_MODE=passcode`). The accounts variables, quotas and the SendGrid secret binding remain on the service, inactive |
| Old demo | `www.the-super-teacher.com` and the bare domain still map to the old `edutrack` service, untouched |

## Incidents today (both caught before any user was affected; there are no external users)

1. **First Litestream deploy failed closed**: wrong URL scheme (`gcs://` instead of `gs://`). The container refused to
   start, traffic stayed on the previous revision. Fixed in #10 and pinned by a real-binary test.
2. **Accounts mode was switched on, then rolled back within minutes.** Sign-in emails could not be sent: SendGrid answered
   `Maximum credits exceeded` (the account's sending allowance was used up; the key itself is valid). The app replied the same
   generic "a link is on its way" regardless, and accounts mode turns the shared passcode off, so nobody could sign in. Rolled
   back to passcode mode (`00008`). Follow-up #16: the provider's reason is now logged, three failures in a row open a breaker
   so the form says "temporarily unavailable" (HTTP 503), and there is an SMTP backend so any provider can be used.

## Blockers before promoting `main` to the live service

1. **Database lineage.** Production's database is stamped with the first accounts migration, numbered `0002`. `main` renumbered
   accounts to `0003` after the data-integrity migration took `0002`, and (correctly, fail closed) refuses to upgrade such a
   database: *"Ambiguous revision 0002 ... refusing to migrate or stamp it"*. Reproduced locally. Options: adopt a snapshot offline with
   `python -m superteacher.adopt_accounts_snapshot` (the release team's bridge, see `docs/IDENTITY_INTEGRATION.md`), or, because
   production holds only a synthetic drill record, start a fresh lineage under a new replica prefix and keep the old one as an archive.
2. **Promotion procedure.** `scripts/deploy_cloud_run.sh` on `main` is the release team's guarded script: explicit service, explicit
   replica prefix, a verified runtime service account, and operator-attested writer drain. Use it; do not bypass it.
3. **Working sign-in email** (below).

## Decisions already made by the owner

* Persistence: Litestream to Cloud Storage.
* Audience: anyone who gives an email address; synthetic data only.
* Open sign-up from `assistant@jordan-kail.com`; conservative AI limits (per user per day: 30 chat messages, 10 insights, 5 parent
  drafts; 300 AI calls per day for the whole demo); cut `www.the-super-teacher.com` over to the new app.

## Not done yet, and why

* **Domain cutover: on hold.** It was approved on the premise that public sign-up would be open. It cannot be, until email works,
  and switching the domain to a login nobody can pass would be worse than the old demo.
* **Needs the owner:** top up or upgrade the SendGrid account, or provide SMTP credentials for another provider
  (`AUTH_EMAIL_BACKEND=smtp`; see `docs/DEPLOYMENT.md`).
* Cutover mechanics when ready: DNS for the domain is hosted at Google Domains and its `www`/apex records already point at Cloud Run, so
  it is a Cloud Run domain-mapping swap only (rollback: map back to `edutrack`). Re-creating a mapping can reprovision the
  certificate, so expect a short HTTPS gap.
* Not verified: real email delivery end to end; cold-start time including a restore; alerting on Litestream restore failures
  (ADR 0001, step 6); the accounts flow against the live service (it ran in a browser on CI only).

## Process notes

* Heavy checks go through `agent-heavy-check`; the shared lock was often busy (exit 75), which is reported, not retried.
* Always re-read a file after `main` moves. A patch of mine to the deploy script was written against a stale copy and would have
  defeated its explicit-prefix guard; it was caught before merge (PR #18 closed unmerged).
