# Release verification checklist

Updated 2026-10-02. Scope: the native checkout at `/home/jkail/projects/superteacher`, excluding `.superdesign`. Current release evidence is below; older iteration checks remain historical. This release operator has not performed production custom-domain cutover.

## Current release checkpoint

Latest exact-CI-verified candidate `9011f65509e5871c8425a99ebaaa4f17b638ab34`
passed all seven exact-source jobs in
[CI37028496201](https://github.com/jckail/superteacher/actions/runs/37028496201):
1357 API tests in 131.56s, 225 web, four browser and 84 E2E tests, plus
lint/types/build, Docker/auth smoke and informational benchmark. The locked Docker
runtime compatibility set passed 259 cases in 35.76s; this is not the full native
API suite inside that image. Reviewed Docker chmod PR63 and documentation PR64
are merged into parent `9011f65`; main and the working branch are pushed.

The immutable archive SHA256
`1ed2b2f022aeaf39e4f22b5aecb0f787b86fe145d8f5b154b20c29e4e4c35d26`
contains 305 entries/276 files, with regular files 0644/0755, directories 0755 and
private roots 0700. Build-helper review passed. Protected session 19785 exited
75 before the helper began: no new intent/proof or cloud call, image digest,
deployment or restore acceptance exists. Do not retry unchanged automatically or
bypass the wrapper; future execution requires fresh capacity and preflight.
B5 `00007-9lq` remains the most recent root-accepted staging release.

Historical 1cde checkpoint: exact source
`1cde1cc24e64599fc03f6a26aad01736960764e2` passed all seven jobs in
[CI37026105054](https://github.com/jckail/superteacher/actions/runs/37026105054)
(1356 API in 182.23s, 225 web, four browser, 84 E2E; locked Docker 259 in 32.34s).
Reviewed PR19/roadmap and five-document checkpoint were integrated in `52d6433`;
that merge differed from 1cde only in documentation. Archive SHA256
`d2b7815c88bc588fe4933ddd9e2a0def0c08bf439dc0a4282991d3b7aa560353`
had 303 entries/274 files and passed source/helper/layout/mode review. Protected
session 7852 exited 75 before helper execution with no intent/proof or cloud call.
Its blocked build is separate from source23's preserved failure and queue blocker;
none establishes a new accepted runtime.

Student follow-up was integrated into the parent in commits:
`037e92f` (original isolated commit `73178da`) adds recorded-detail cutoff/
forward-day refresh, ordinary-error draft retention, fatal typed404 handling and
actual write-ordering regressions (35 new tests). `7e9b627` (original `79f85f3`)
adds captured delete-target/client/lifecycle handling (11 new cases). Both tasks
and the full branch diff have independent specification and quality approval with
no actionable findings. Original worktree:
`/home/jkail/projects/superteacher-student-freshness-20261002`.
Root-executed final focused evidence is 80 tests across eight files in 7.04s, with
types, focused lint and diff checks passing. Integration is local; publication,
full combined exact CI and runtime acceptance remain pending. The 9011 CI does
not cover these new commits. Independent Insight, generated-draft provenance and
new-after-submit note settlement remain separate. Opening note B during a pending
note-A modal has not been established as reachable; note/accessibility audits
remain ongoing, without a confirmed interaction claim from that scenario.

Earlier source23 candidate (historical CI/artifact/blocker):

Exact release candidate `23f5ed0ff3ab2c7eddc88a027baaa5729231647c` passed all seven exact-source
jobs in [CI37022756475](https://github.com/jckail/superteacher/actions/runs/37022756475): 1350 API, 225 web, four browser,
84 E2E and 259 actual Docker-runtime compatibility cases, plus lint/types/build,
Docker/auth smoke and informational benchmark. Reports Summary freshness and
SMTP breaker corrections have source/CI acceptance; no real SMTP/provider delivery
is proved. Corrected keyboard response barriers preserve the original test checks.

The first immutable artifact built successfully (`e866d260-390c-4fbb-90d5-c35688966f11`,
digest `66df34171a6ee17ae027840f7945f056471ddcaf01a0e15fea608af96f03a35d`), but owned
staging `00008-6cj` failed on unreadable mode 0600 `/app/litestream.yml`. B5 remains
the latest Ready at 100% accepted staging artifact. The reviewed same-archive corrected
context has readable 0644/0755 files and directories 0755, private 0700 roots and
exclusive separate outputs/tag. Protected corrected build session 7798 exited 75 before helper execution; no
build-b intent/proof or cloud call occurred. No corrected build/deploy/recovery
acceptance exists; do not retry the unchanged blocked action.

Runtime IAM permission probe passed; protected rehearsal exited 75 before helper
execution, so runtime acceptance remains pending. Production promotion/domain
cutover and broader model/provider acceptance remain open. Preserve failed artifacts
and never bypass or repeat an unchanged lock-blocked action.

Historical PR19/roadmap integration and 1cde exact CI are recorded above; neither
source23 nor 1cde evidence substitutes for the distinct 9011 runtime gate.

Latest verified serving staging release (B5):

Reviewed source `b5c1b8d00294afce0ebb5228b3be1c3a423d6191` serves isolated
staging revision `00007-9lq`.
[CI37013321634](https://github.com/jckail/superteacher/actions/runs/37013321634)
passed all seven jobs: 1312 API without skips/xfails, 207 web, four browser and
83 E2E cases, lint/types/build, Docker/auth smoke and informational benchmark.
Overview captured `as_of` and scoped forward-day refresh passed independent
backend/client review and focused checks. Native mean/order/top-eight retention
remain unchanged. Actual Python 3.12.15 runtime compatibility evidence remains
259 passing cases.

Protected immutable Cloud Build `42d93f52-189c-43b6-a954-8e243690bda4` succeeded;
image digest `719f06c8f9da2ec4f77dcf97141e88244f4a6bdc289256c46e3f227acf5248b5`
and the fresh source-bound replica prefix are recorded in the deployment ledger.
Synthetic Overview/cutoff/summary/history/precision, paging/exports/preflight and
logout checks passed. Recovery-only execution
`superteacher-overhaul-recovery-b5c1b8d-b7l4d` succeeded at 13:51:10 UTC with
integrity/FKs/head `0003`, history and both raw-score proofs; structured recovery
and staging receipt readback passed. Final-image runtime inventory matches all 39
prior observed package resolutions. Production traffic/domains are unchanged;
final drain and zero-loss RPO are not proved. Dedicated runtime IAM resources are
provisioned separately, with runtime acceptance still pending. Other consumers'
date freshness, full grading model and production cutover remain open.

Previous verified Overview retention and runtime release:

Reviewed source `c3277b4` previously served isolated staging revision `00006-fl2`.
[CI37010699744](https://github.com/jckail/superteacher/actions/runs/37010699744)
passed all gates: 1309 API without skips/xfails, 194 web, four browser and 83 E2E
cases. Actual Python 3.12.15 image checks passed version/UID/imports/inventory,
259 focused runtime compatibility cases and existing restricted-directory auth/
startup smoke. Root's 95 Overview regressions and independent reviews passed.
Protected immutable build and synthetic Overview/summary/cutoff/history/precision,
export/preflight/logout checks passed. Recovery-only execution
`superteacher-overhaul-recovery-c3277b4-hlwcb` succeeded at 13:20:46 UTC; structured
integrity/FKs/head `0003`, history and both raw-score proofs passed. Final-image
Python 3.12.15/inventory and staging receipt readback passed. All 39 prior observed
package resolutions matched; no final drain or zero-loss RPO claim. Exact evidence
belongs in the deployment ledger. Production traffic and custom-domain mappings remain unchanged.

Previous verified summary and calendar release:

Reviewed source `07974de` previously served isolated staging revision `00005-klh`.
[CI37007214732](https://github.com/jckail/superteacher/actions/runs/37007214732)
passed all gates: 1294 API without skips/xfails, 194 web, four browser and 83 E2E
cases, including real PostgreSQL summary cursors and restricted-directory Docker
startup. Protected immutable-image build and synthetic summary/Gradebook-cutoff,
transfer/history/precision, paging/CSV/account, section-preflight and logout checks
passed. Recovery-only execution `superteacher-overhaul-recovery-07974de-xq7gr`
succeeded at 12:56:40 UTC with integrity/FKs/head `0003`, transfer/history and both
raw scores preserved. Structured proofs and staging receipt readback passed.
This does not prove final production drain or zero-loss RPO. Exact artifact
bindings and prior failure evidence are in [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md).
Production traffic and custom-domain mappings remain unchanged. At that checkpoint, runtime and
Overview retention were pending; they subsequently shipped in `c3277b4`, and
Overview date freshness in `b5c1b8d`. Broader model/production acceptance remains open.

Previous verified release:

Reviewed source `4f7ba66` previously served isolated staging revision `00004-hlb`.
[CI37003990788](https://github.com/jckail/superteacher/actions/runs/37003990788)
passed all gates: 1266 API tests without skips/xfails, 184 web, four browser and
83 E2E cases. Its Docker smoke reproduces restricted release-directory permissions.
Protected immutable-image build succeeded, and synthetic HTTP workflows, scoped
cursor/CSV/account exports, raw historical precision, section preflight and
copied-cookie logout passed. Independent read-only replica recovery execution
`superteacher-overhaul-recovery-4f7ba66-p4rlv` succeeded at 12:12:26 UTC; integrity,
native head `0003`, transfer/history and raw precision passed. Staging receipt
readback also passed. This is not a final production drain or zero-loss RPO claim.
Source/artifact/prefix bindings and preserved failure evidence are recorded in
[DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md). Production remains unchanged.
Class-summary and Gradebook calendar follow-ups shipped in `07974de`; the full
grading model and original overhaul remain active.

Earlier successful release:

Reviewed source `3e6629c` adds roster API/client pagination and
CSV/account JSON streaming. Root focused verification: 67 pagination/CSV,
12 account stream, two CORS and 50 frontend/session cases passed. Two new
PostgreSQL integration cases skipped locally, then executed in exact-source
[CI36996126364](https://github.com/jckail/superteacher/actions/runs/36996126364):
1195 API tests without skips/xfails, 137 web tests, four browser tests and 83 E2E
tests passed. All required lint/types/build/Docker gates and benchmark passed.
Protected Cloud Build `3bc0704a-fe6a-4264-80b8-e1ef47ec0b8b` succeeded;
the immutable digest previously served isolated staging revision `00002-jqp` with fresh
storage, AI/demo disabled and max one instance. Synthetic writes/transfer/history,
raw precision, cursor scope/counts, CSV/account exports and copied-cookie logout
passed. Recovery-only execution `superteacher-overhaul-recovery-3e6629c-k4hx7`
succeeded at 11:00:15 UTC, checking integrity/FKs/head `0003`, transfer/history
and raw precision in a fresh restored copy. Staging receipt readback passed;
production restart/final drain/zero-loss RPO remain unproven. Exact image/prefix/source archive
evidence is in [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md). Production traffic
and custom-domain mappings remain unchanged; the full overhaul is active.

Historical release evidence follows:

Source `881a2af` passed all gates in
[CI36989700391](https://github.com/jckail/superteacher/actions/runs/36989700391):
1113 API tests with the copied-cookie logout regression passing, 119 web tests,
4 browser tests, 82 E2E tests, strict types/lint, frontend build and Docker
build/auth smoke. Server-revocable passcode sessions are independently reviewed;
no migration is needed, and v1 cookies require one new sign-in after release.
The new-source protected image build stopped at shared-lock exit 75 before Cloud
Build began; log /tmp/st-release-881a2af-build.log. No new serving image or
production/staging deployment occurred; do not retry unchanged or bypass the lock.

Earlier integrated release evidence follows:

Source `c2812f4` passed all gates in
[CI36987004974](https://github.com/jckail/superteacher/actions/runs/36987004974):
1081 API tests and one known passcode-logout xfail, 119 web tests, 4 browser tests,
82 E2E tests, strict types/lint, frontend build and Docker build/auth smoke. The
legacy roster adapter has independent review and an exact private archive
conversion/recovery proof (11 courses, 33 sections, 30 students; no fabricated
events). All converted students truthfully derive unknown risk. The source and
converted bundle have verified private GCS hash roundtrips. A new serving image
build stopped at shared-lock exit 75 before Cloud Build; staging remains7166813,
production services and domain mappings were not changed. Do not retry the
unchanged build or bypass the lock. Full overhaul remains active; auth release,
archive access, final dataset/owner decisions and production cutover are open.

Earlier integrated release evidence follows:

PR15 merged source7166813 into main8ceb050. Subsequent main5113de8 passed
[CI36978867068](https://github.com/jckail/superteacher/actions/runs/36978867068):
all six required jobs plus informational benchmark, **996 API tests, one known
legacy-passcode logout xfail**. Source7166813 has an immutable built image,
isolated authenticated/synthetic staging verification and a successful independent
replica restore. Exact image, revision and limits are in
[DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md). The earlier9de97ce image build
stopped at shared verification-lock exit 75 before any cloud build began.

Corrected-helper adoption on a private restored production copy also passed in
recovery-only executionhbrzh, using a checked helper artifact in runtime7166813.
It did not build/validate a newer serving image or change the live schema.
Still required: fresh post-drain adoption, production legacy dataset/owner mapping,
compatible rollback, observed final writer drain and public-domain acceptance.
See [LEGACY_CUTOVER.md](LEGACY_CUTOVER.md) and the drain protocol below.

## Historical iteration evidence (2026-10-01)

| Check | Verified result |
| --- | --- |
| Focused backend checks | Root reported 53 passing cases before integrating newer origin/main; rerun release CI on the final merged commit. |
| Roster write/read races | Root reported all 9 `RosterWrite.test.tsx` cases passing after scoping dialog live-region queries. |
| Authentication transport | Root reported 15 passing cases. |
| Strict frontend TypeScript and ESLint | Root reported passing against the settled source. |
| Native broad verification | Not started: `agent-heavy-check` returned exit 75 while the shared lock was occupied. Do not report a full local suite/build as passed. |
| Candidate source scan | 143 text files inspected, excluding `.superdesign`; no private-key markers or recognized provider-token patterns found. No candidate symlinks or files over 2 MB were reported. This bounded scan is not proof that all secret formats are absent. |
| Git staging at audit | No staged diff was present. Modified files, deleted JavaScript predecessors and untracked TypeScript replacements must be staged together before recording the release commit. |

## Source and packaging review

- [ ] Exclude `.superdesign`, `.env` variants, session secrets, databases/WAL files, Terraform state/variable files, dependencies and browser traces from the release commit. Review the actual staged file list and diff after staging. Terraform's local ignore rules exclude its state, plans and variable files; root ignores browser output and database sidecars.
- [x] Hardened ignore rules after review: `.gitignore` excludes `.env.*` with an `.env.example` exception; `.dockerignore` excludes `.session_secret`, Python virtual environments and frontend coverage. `.superdesign` remains excluded from Docker/Cloud Build context. `.gcloudignore` already excludes session secrets and the native virtual environment. Root must still review actual staged candidates.
- [x] Migrated UI entrypoint is `/src/main.tsx`; strict `tsconfig.json` includes source, Vite config and browser tests. Vitest discovers TypeScript tests. Docker copies the full `web/` source and runs its production build, then copies only `web/dist` into the runtime stage. Include the new TS/TSX files, config and package lock with the JSX/JS deletions.
- [x] Calendar source binds one school day per HTTP operation and retains the configured timezone for WebSockets. Cloud Build passes `_SCHOOL_TIMEZONE`, default UTC; settings validate the IANA zone, and `tzdata` is a runtime dependency.
- [x] Course creation accepts optional `initial_section_name`, appends its section before a single transaction commit, and rolls back both objects on an integrity failure. Bare course creation still returns an empty section list. The new-course dialog makes one POST with `initial_section_name: 'Period 1'`; focused backend/frontend cases cover this contract.

## GitHub CI proof gate

The current workflow triggers on pushes to `main` and on pull requests. A release-branch push alone does not start it: open a pull request or deliberately enable a suitable trigger before relying on CI.

Root will push the release branch and open a PR to start broad GitHub CI while the native shared verification lock is occupied. After merging newer origin/main source, preserve these release guards and use CI for the final merged candidate. Record the immutable release commit, PR URL, workflow run URL and successful job conclusions below before deploying its image. A run for a different commit does not satisfy this gate.

- Exact CI-verified release candidate: `9011f65509e5871c8425a99ebaaa4f17b638ab34`
- Current candidate CI: [37028496201, all seven jobs passed](https://github.com/jckail/superteacher/actions/runs/37028496201)
- Latest accepted isolated staging: B5 `00007-9lq` at 100%; 9011 build remains blocked before helper execution.

Historical PR15 checkpoint:

- Then-verified source: `5113de89c4625e61b8e2ab5ff1aac6378bf116ff`
- Pull request: [PR15, merged](https://github.com/jckail/superteacher/pull/15)
- Then-current CI: [36978867068, all gates passed](https://github.com/jckail/superteacher/actions/runs/36978867068)
- Staged source7166813 image: `sha256:5d3c85dfb754bf5382ca7f196d86b108d878c2a85ccf2425702d22b0df7bcde6`
- Latest9de97ce image: blocked before build; not deployed.

| Required CI job | Actual configured gate | Proof still needed |
| --- | --- | --- |
| `lint` | Ruff check and formatting check on Python 3.12. | Successful conclusion for release commit. |
| `api` | Full `python -m pytest -q`; PostgreSQL 17 service supplies `ST_TEST_POSTGRES_URL`. Two dedicated PostgreSQL tests exercise migrations/persistence, grade constraints and extra-credit/invalid-score constraints. Installs pinned, checksum-verified Litestream 0.5.17 so real restore/replicate round-trip cases can execute. | Successful conclusion with PostgreSQL cases executed, not skipped. |
| `web` | Node 22, clean npm install, ESLint, full Vitest with two workers and production build. Build includes strict TypeScript. | Successful conclusion for release commit. |
| `browser` | Builds UI and runs Chromium workflows against FastAPI with a temporary migrated SQLite database, test passcode and no live AI credentials; one worker. | Successful conclusion for release commit; review retained failure artifacts if failed. |
| `e2e` | Incoming main Playwright/axe workflow suite with empty and seeded synthetic databases, one worker and retained failure artifacts; builds the migrated UI. | Successful conclusion for release commit. |
| `docker` | Waits for all five other jobs, builds image, checks unauthenticated API 401 and SPA root, polls public health, explicitly requires final health HTTP 200, verifies readiness/login/authenticated overview/calendar/logout, and checks startup refusal without a password. | Successful conclusion for release commit; final readiness assertion added during this audit. |

## Gates CI does not establish

- [x] Source7166813 isolated candidate passed public health/readiness, protected401, actual login, overview/calendar/version/SPA/logout and synthetic write/transfer-history checks. This does not satisfy production custom-domain acceptance or checks for a later image.
- [ ] If full API/browser workflows against PostgreSQL are required, run or add that acceptance gate. The generic pytest fixtures use in-memory SQLite; the browser harness explicitly uses disposable SQLite. The two PostgreSQL integration tests do not prove the full application workflow on PostgreSQL or a Cloud SQL Unix socket.
- [x] Accepted Litestream pilot: isolated restore passed integrity/FKs/native head `0003` and exact synthetic transfer/grade receipt checks. Production restart, zero-loss RPO and final production schema adoption remain unproven.
- [ ] Complete the data-preservation and restore prerequisites in [RELEASE_PLAN.md](RELEASE_PLAN.md) and [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) before replacing a serving revision. The older inventory has been superseded: a ce94d50 image now uses a Litestream replica. Existence of replica objects alone does not prove recovery or a safe single-writer handoff; recheck current configuration before acting.
- [ ] Record the intended target explicitly. The observed custom domains map to `edutrack`, while `superteacher` is a separate service. A deployment to `superteacher` alone does not update those domains. Record prior revision/rollback procedure and validate the selected route after cutover.
- [ ] Review identity/data-retention prerequisites from [RELEASE_PLAN.md](RELEASE_PLAN.md). Source includes email accounts, server-revocable sessions and tenant-scoped records with negative authorization tests; deployed staging uses the existing passcode policy. Production email enablement/owner/sender configuration remains separate operator information.

Source references: `.github/workflows/ci.yml`, `Dockerfile`, ignore files, `cloudbuild.yaml`, `web/package.json`, `web/index.html`, `web/tsconfig.json`, `web/vite.config.ts`, `web/playwright.config.ts`, `scripts/e2e_server.py`, `tests/conftest.py`, `tests/test_postgres.py`, `tests/test_course_creation.py`, `superteacher/calendar.py`, `superteacher/schemas.py`, `superteacher/routers/roster.py`, `web/src/pages/Roster.tsx`, and the deployment/calendar/backup documents linked above.


## Single-writer production drain protocol

This is a proposed execution gate for the root deployment owner; the research agent made no cloud changes. Coordinate with any other deployment owner before running it. Latest observed service: `portfolio-383615/us-central1/superteacher`, revision `superteacher-00005-bmx`, created 2026-10-02 04:48:32 UTC, image digest `sha256:e9757073f09b46f0b3b9f01d056e12c8cdc63978d660d44bebbab079c4a39b72`, `VERSION=ce94d50`. Its environment names include the new `DRILL`; that suggests a configuration/restore drill but does not identify the owner. At 04:59:07 UTC the latest 04:58 metric sample showed active=0, idle=1: a runtime still existed. No drain is claimed.

1. Record the old revision/image, explicit replica prefix and rollback choice. Confirm the other deployment owner has stopped changes. Inventory traffic tags; tagged revisions can remain callable while the main service is disabled. Avoid any candidate tag or staging service using the live replica prefix.
2. The authorized execution owner can disable the untagged service with `gcloud run services update superteacher --project=portfolio-383615 --region=us-central1 --scaling=0`. Re-read service scaling/traffic metadata and record completion time. This does not create a revision; existing requests may finish. [Google manual-scaling documentation](https://docs.cloud.google.com/run/docs/configuring/services/manual-scaling) describes the command and tag exception.
3. Confirm complete runtime drainage using `run.googleapis.com/container/instance_count` filtered to resource type `cloud_run_revision`, service `superteacher`, region `us-central1`, across every old revision and both active/idle states. Require explicit zero samples dated after the drain, then recheck before promotion. Sampling is every 60 seconds with up to 120 seconds additional visibility delay. Missing or stale series cannot be interpreted as zero. [Metric definition](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z).
4. Correlate system/container shutdown evidence by revision and instance ID. Cloud Run sends SIGTERM, then SIGKILL after its grace period. Uvicorn shutdown logs alone are insufficient: PID 1 runs Litestream, which can still sync after the app exits. A disabled URL, traffic=0%, Ready status or a fixed sleep alone does not establish no writer. [Runtime shutdown contract](https://docs.cloud.google.com/run/docs/container-contract).
5. Only after the writer gate passes, restore/promote the approved candidate while preserving manual scaling=0, then re-enable exactly one permitted runtime after routing references only the intended revision. Validate version, authentication and persistence. Rollback must follow the same drain gate before another revision restores/writes the live prefix; never revive an older database snapshot without reviewing post-cutover writes.

For Monitoring API reads, use the `projects/portfolio-383615/timeSeries` endpoint with the filter above, a time window spanning the disable operation, and `view=FULL`. Inspect raw timestamps/state labels; no aggregation may discard idle instances. Fetch access tokens only into process memory and never print them. The preview standalone Cloud Run instance-list API is a different workload and does not enumerate service containers.

Scale integration adds an informational `bench-smoke` artifact job (1,000 synthetic students,15runs). It does not substitute for correctness gates or prove production capacity. Root added authenticated Docker readiness/login/calendar/logout smoke after the first PR15 run. Initial exact-commit CI36967196648 results and diagnosed failures are recorded in OVERHAUL_AUDIT.md; final passing evidence remains pending for the replacement commit.
