# Release checkpoint (2026-10-02)

What is verified, what is not, and the gates before the public domain moves. Facts here were observed in this session;
anything not observed is listed under "Not verified".

## Code on `main` (`ce94d50`)

PRs #1 to #10 merged: overhaul, hygiene, observability (#4), decision records (#5), security review (#6) and its patches
(#8), E2E + accessibility suite (#7), Litestream persistence (#9) and its scheme fix (#10). CI on #9 and #10: `api`,
`docker`, `e2e`, `lint`, `web` all passed.

## Production: Cloud Run `superteacher` (project `portfolio-383615`, `us-central1`)

| Item | Observed |
|---|---|
| Serving revision | `superteacher-00005-bmx`, 100% traffic, image built from `main` |
| URL | https://superteacher-vbufkr2qma-uc.a.run.app (also `...-292025398859.us-central1.run.app`) |
| Auth | shared passcode (`AUTH_MODE` not set, so passcode mode); `/api/overview` is 401 without a session |
| Persistence | Litestream 0.5.17 to `gs://portfolio-383615-superteacher-litestream/superteacher` |
| Bucket | private (public access prevention enforced), uniform access, versioned, noncurrent versions deleted after 14 days, `objectAdmin` granted to the runtime service account only |
| Scaling | `max-instances=1`, `min-instances=0` (SQLite is single-writer) |

### Persistence gate: PASSED

Drill (synthetic data, then cleaned up): wrote a course, section and student on revision `00004`; replica objects
appeared in the bucket; forced a new revision (`00005`, new instance, empty disk) with no overlapping writer; read the
records back: **survived**. The drill record was deleted afterwards (the empty "Drill Course" remains: courses have no
delete endpoint).

### Incident worth remembering

The first deploy of #9 failed to start: `unknown replica type in config: "gcs"`. Litestream's scheme is `gs://`.
The container refused to start (restore failed closed), traffic stayed on the previous revision, and nothing was
lost. Fixed in #10; a test now pins the scheme against the real binary and CI downloads that binary.
A second catch the same way: CI's Docker smoke test found the entrypoint script was committed without the executable bit.

## Gates before `www.the-super-teacher.com` moves to this service

1. Persistence drilled in production: **done** (above).
2. Per-user accounts, if the app is opened to anyone with an email: PR #12, **not merged**, CI and review pending.
3. Owner go-ahead for the domain-mapping swap. Not requested yet. DNS for the domain is hosted at Google Domains
   (no API), but its `www` and apex records already point at Cloud Run, so the cutover is a Cloud Run domain-mapping
   change only. Rollback: remap the domain to the old `edutrack` service.
4. Do not change the old `edutrack` service until then: it still serves `www.the-super-teacher.com`.

## Open work

| PR | State | Note |
|---|---|---|
| #11 scale benchmarks and query-plan guards | `api` check red | The attendance query plan guard fails on GitHub's SQLite. The release team is fixing the query separately (commit `26d27f9`); do not duplicate it here |
| #12 accounts (passwordless email, tenancy) | CI pending | `AUTH_MODE` defaults to `passcode`; migration id `0002` can collide with another worker's `0002_data_integrity` |

## Not verified

* The accounts flow end to end: its Playwright spec was authored but never run locally.
* A full-suite run with the final accounts code (the heavy-check lock was busy).
* Cold-start time including the restore on a real instance (not measured).
* Alerting on Litestream restore failures (ADR 0001 step 6) is not configured.
* Real SendGrid delivery for sign-in emails.
