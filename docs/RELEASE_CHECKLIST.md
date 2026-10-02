# Release verification checklist

Audit date: 2026-10-01. Scope: the native checkout at `/home/jkail/projects/superteacher`, excluding `.superdesign`. This file records observed source and root-agent check results; it does not assert that a published candidate or deployment has passed.

## Current evidence

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

- Release commit: pending
- Pull request: pending
- CI run: pending
- Image digest: pending

| Required CI job | Actual configured gate | Proof still needed |
| --- | --- | --- |
| `lint` | Ruff check and formatting check on Python 3.12. | Successful conclusion for release commit. |
| `api` | Full `python -m pytest -q`; PostgreSQL 17 service supplies `ST_TEST_POSTGRES_URL`. Two dedicated PostgreSQL tests exercise migrations/persistence, grade constraints and extra-credit/invalid-score constraints. Installs pinned, checksum-verified Litestream 0.5.17 so real restore/replicate round-trip cases can execute. | Successful conclusion with PostgreSQL cases executed, not skipped. |
| `web` | Node 22, clean npm install, ESLint, full Vitest with two workers and production build. Build includes strict TypeScript. | Successful conclusion for release commit. |
| `browser` | Builds UI and runs Chromium workflows against FastAPI with a temporary migrated SQLite database, test passcode and no live AI credentials; one worker. | Successful conclusion for release commit; review retained failure artifacts if failed. |
| `e2e` | Incoming main Playwright/axe workflow suite with empty and seeded synthetic databases, one worker and retained failure artifacts; builds the migrated UI. | Successful conclusion for release commit. |
| `docker` | Waits for all five other jobs, builds image, checks unauthenticated API 401 and SPA root, polls public health, explicitly requires final health HTTP 200, and checks startup refusal without a password. | Successful conclusion for release commit; final readiness assertion added during this audit. |

## Gates CI does not establish

- [ ] Obtain an authenticated smoke result for the actual candidate image/deployment: public healthy response, protected API 401 before login, successful login and authenticated overview, served SPA, expected `/api/version`, and logout/session behavior. `deployment_tests.py` provides part of this check but is not invoked by the current Docker job.
- [ ] If full API/browser workflows against PostgreSQL are required, run or add that acceptance gate. The generic pytest fixtures use in-memory SQLite; the browser harness explicitly uses disposable SQLite. The two PostgreSQL integration tests do not prove the full application workflow on PostgreSQL or a Cloud SQL Unix socket.
- [ ] Verify the approved persistence branch: PostgreSQL/Cloud SQL when selected, or the accepted Litestream pilot from ADR 0001 with a validated isolated restore path. Verify migration head `0002`, school timezone and secret/replica access. Prove persistence across a candidate revision/restart through an authorized procedure.
- [ ] Complete the data-preservation and restore prerequisites in [RELEASE_PLAN.md](RELEASE_PLAN.md) and [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) before replacing a serving revision. The older inventory has been superseded: a ce94d50 image now uses a Litestream replica. Existence of replica objects alone does not prove recovery or a safe single-writer handoff; recheck current configuration before acting.
- [ ] Record the intended target explicitly. The observed custom domains map to `edutrack`, while `superteacher` is a separate service. A deployment to `superteacher` alone does not update those domains. Record prior revision/rollback procedure and validate the selected route after cutover.
- [ ] Review identity/data-retention prerequisites from [RELEASE_PLAN.md](RELEASE_PLAN.md). Current authentication grants a shared dataset through one passcode; CI does not validate a multi-teacher identity policy.

Source references: `.github/workflows/ci.yml`, `Dockerfile`, ignore files, `cloudbuild.yaml`, `web/package.json`, `web/index.html`, `web/tsconfig.json`, `web/vite.config.ts`, `web/playwright.config.ts`, `scripts/e2e_server.py`, `tests/conftest.py`, `tests/test_postgres.py`, `tests/test_course_creation.py`, `superteacher/calendar.py`, `superteacher/schemas.py`, `superteacher/routers/roster.py`, `web/src/pages/Roster.tsx`, and the deployment/calendar/backup documents linked above.


## Single-writer production drain protocol

This is a proposed execution gate for the root deployment owner; the research agent made no cloud changes. Coordinate with any other deployment owner before running it. Latest observed service: `portfolio-383615/us-central1/superteacher`, revision `superteacher-00005-bmx`, created 2026-10-02 04:48:32 UTC, image digest `sha256:e9757073f09b46f0b3b9f01d056e12c8cdc63978d660d44bebbab079c4a39b72`, `VERSION=ce94d50`. Its environment names include the new `DRILL`; that suggests a configuration/restore drill but does not identify the owner. At 04:59:07 UTC the latest 04:58 metric sample showed active=0, idle=1: a runtime still existed. No drain is claimed.

1. Record the old revision/image, explicit replica prefix and rollback choice. Confirm the other deployment owner has stopped changes. Inventory traffic tags; tagged revisions can remain callable while the main service is disabled. Avoid any candidate tag or staging service using the live replica prefix.
2. The authorized execution owner can disable the untagged service with `gcloud run services update superteacher --project=portfolio-383615 --region=us-central1 --scaling=0`. Re-read service scaling/traffic metadata and record completion time. This does not create a revision; existing requests may finish. [Google manual-scaling documentation](https://docs.cloud.google.com/run/docs/configuring/services/manual-scaling) describes the command and tag exception.
3. Confirm complete runtime drainage using `run.googleapis.com/container/instance_count` filtered to resource type `cloud_run_revision`, service `superteacher`, region `us-central1`, across every old revision and both active/idle states. Require explicit zero samples dated after the drain, then recheck before promotion. Sampling is every 60 seconds with up to 120 seconds additional visibility delay. Missing or stale series cannot be interpreted as zero. [Metric definition](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z).
4. Correlate system/container shutdown evidence by revision and instance ID. Cloud Run sends SIGTERM, then SIGKILL after its grace period. Uvicorn shutdown logs alone are insufficient: PID 1 runs Litestream, which can still sync after the app exits. A disabled URL, traffic=0%, Ready status or a fixed sleep alone does not establish no writer. [Runtime shutdown contract](https://docs.cloud.google.com/run/docs/container-contract).
5. Only after the writer gate passes, restore/promote the approved candidate while preserving manual scaling=0, then re-enable exactly one permitted runtime after routing references only the intended revision. Validate version, authentication and persistence. Rollback must follow the same drain gate before another revision restores/writes the live prefix; never revive an older database snapshot without reviewing post-cutover writes.

For Monitoring API reads, use the `projects/portfolio-383615/timeSeries` endpoint with the filter above, a time window spanning the disable operation, and `view=FULL`. Inspect raw timestamps/state labels; no aggregation may discard idle instances. Fetch access tokens only into process memory and never print them. The preview standalone Cloud Run instance-list API is a different workload and does not enumerate service containers.
