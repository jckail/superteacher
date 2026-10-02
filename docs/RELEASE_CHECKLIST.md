# Release verification checklist

Audit date: 2026-10-01. Scope: the native checkout at `/home/jkail/projects/superteacher`, excluding `.superdesign`. This file records observed source and root-agent check results; it does not assert that a published candidate or deployment has passed.

## Current evidence

| Check | Verified result |
| --- | --- |
| Focused backend checks | Root reported 53 passing cases. |
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
| `api` | Full `python -m pytest -q`; PostgreSQL 17 service supplies `ST_TEST_POSTGRES_URL`. Two dedicated PostgreSQL tests exercise migrations/persistence, grade constraints and extra-credit/invalid-score constraints. | Successful conclusion with PostgreSQL cases executed, not skipped. |
| `web` | Node 22, clean npm install, ESLint, full Vitest with two workers and production build. Build includes strict TypeScript. | Successful conclusion for release commit. |
| `browser` | Builds UI and runs Chromium workflows against FastAPI with a temporary migrated SQLite database, test passcode and no live AI credentials; one worker. | Successful conclusion for release commit; review retained failure artifacts if failed. |
| `docker` | Waits for all four jobs, builds image, checks unauthenticated API 401 and SPA root, polls public health, explicitly requires final health HTTP 200, and checks startup refusal without a password. | Successful conclusion for release commit; final readiness assertion added during this audit. |

## Gates CI does not establish

- [ ] Obtain an authenticated smoke result for the actual candidate image/deployment: public healthy response, protected API 401 before login, successful login and authenticated overview, served SPA, expected `/api/version`, and logout/session behavior. `deployment_tests.py` provides part of this check but is not invoked by the current Docker job.
- [ ] If full API/browser workflows against PostgreSQL are required, run or add that acceptance gate. The generic pytest fixtures use in-memory SQLite; the browser harness explicitly uses disposable SQLite. The two PostgreSQL integration tests do not prove the full application workflow on PostgreSQL or a Cloud SQL Unix socket.
- [ ] Verify the deployed candidate's PostgreSQL identity, migration head `0002`, approved school timezone, Cloud SQL connection and secret access. Prove data persistence across a candidate revision/restart and inspect record counts using an authorized procedure.
- [ ] Complete the data-preservation and restore prerequisites in [RELEASE_PLAN.md](RELEASE_PLAN.md) and [BACKUP_RECOVERY.md](BACKUP_RECOVERY.md) before replacing a serving revision. The earlier read-only inventory found no configured durable database on `superteacher`; recheck current configuration before acting.
- [ ] Record the intended target explicitly. The observed custom domains map to `edutrack`, while `superteacher` is a separate service. A deployment to `superteacher` alone does not update those domains. Record prior revision/rollback procedure and validate the selected route after cutover.
- [ ] Review identity/data-retention prerequisites from [RELEASE_PLAN.md](RELEASE_PLAN.md). Current authentication grants a shared dataset through one passcode; CI does not validate a multi-teacher identity policy.

Source references: `.github/workflows/ci.yml`, `Dockerfile`, ignore files, `cloudbuild.yaml`, `web/package.json`, `web/index.html`, `web/tsconfig.json`, `web/vite.config.ts`, `web/playwright.config.ts`, `scripts/e2e_server.py`, `tests/conftest.py`, `tests/test_postgres.py`, `tests/test_course_creation.py`, `superteacher/calendar.py`, `superteacher/schemas.py`, `superteacher/routers/roster.py`, `web/src/pages/Roster.tsx`, and the deployment/calendar/backup documents linked above.
