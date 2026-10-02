# Super Teacher overhaul: evidence and remaining work

Updated 2026-10-02, working repository `superteacher`. Earlier checkpoint entries below are historical; the current release ledger is `DEPLOYMENT_STATUS.md`. This is a living implementation and acceptance ledger. Source is being edited concurrently; recheck the cited files and rerun checks before closing any item.

## Original objective and completion standard

The requested work is a deep overhaul of the app at https://www.the-super-teacher.com/ and this repository: frontend, backend, AI features, data model, architecture, reliability, and TypeScript migration. TypeScript conversion is one requirement within that scope. Passing existing unit tests alone does not prove a comprehensive product overhaul, a usable production deployment, or production data safety.

Completion requires an integrated implementation, passing relevant checks, representative browser workflows, validated persistence and migration behavior, and evidence that the intended release actually runs at the public host. Account/tenancy design, grading policy, retention policy, and deployment topology need explicit product decisions before implementing their final form. Record those decisions here instead of silently assuming that the existing single-teacher design is the desired final state.

## Verified implementation baseline

Current release `07974de` passed every exact CI gate (1294 API, 194 web, four
browser, 83 E2E tests) and serves isolated staging revision `00005-klh`. It adds
reviewed class-summary column reads/batches, server Gradebook cutoff and forward
school-day refresh, and truthful template wording to the earlier saved-scope,
Reports picker, archive-viewer and container-permission fixes. Real PostgreSQL
summary cursor parity passed. Synthetic HTTP summary/cutoff, workflow/export,
history/raw precision and logout checks passed. Independent recovery-only
execution `07974de-xq7gr` passed integrity/FKs/head `0003`, history and both raw
scores at 12:56:40 UTC; subsequent staging receipt readback passed. Earlier
`4f7ba66` restore evidence is preserved. Production traffic and domains remain unchanged.
See the deployment ledger for exact artifact bindings and preserved failure evidence.

Earlier feature milestone through `c95d9f9`: independently reviewed roster API
and client pagination, CSV streaming and account JSON streaming. Root verified
67 pagination/CSV, 12 account-stream, two CORS and 50 frontend/session focused
cases. Two added PostgreSQL cases require the real CI service and skipped locally.
Full history scans/CPU, assessment width, single large records and browser blob
buffering remain distinct from bounded ranking/output/fetch batches. Broad
exact-head verification and a new serving image subsequently passed as recorded
above; the deployment ledger separates staging from production acceptance.

These statements describe inspected source, not a claim that every current check passes or that the public host serves this code.

| Area | Current source evidence | Verification boundary |
| --- | --- | --- |
| Browser application | Application pages and components are now `.ts`/`.tsx`; `web/tsconfig.json` enables strict checking; `web/src/types.ts` contains response and request DTOs. | All browser source and tests now use TypeScript and the strict typecheck includes tests. Runtime/browser coverage still needs expansion. |
| API/service boundaries | FastAPI routers, reusable queries, pure derived metrics, reports, and AI services exist separately. `tests/test_architecture.py` guards service-to-router imports. | Structural coverage does not validate all business behavior or production configuration. |
| Data model | `superteacher/models.py` uses relational courses, sections, students, assessments, scores, attendance, notes, and insight cache. Foreign keys and score/attendance uniqueness exist; SQLite enables foreign keys in `db.py`. | Revision 0002 enforces numeric/enum constraints; revision 0003 adds accounts and course ownership. Dated enrollment, academic terms and general audit history remain open. |
| Data consistency | `queries.py` streams history in bounded batches for AI summaries; `metrics.py` centralizes grades, risk, homework, and attendance. Student transfers preserve prior scores; active metrics filter to the current section and a scoped grade-history endpoint exposes previous-section records. | Query count is distinct from bounded row count, memory, and latency. Grades now survive section transfers. Grading weights, academic terms and dated enrollment semantics still need product decisions. |
| Authentication | `auth.py` requires a configured passcode unless explicitly disabled, signs session cookies, checks request/WebSocket origins, and throttles login attempts. | Source also supports email accounts, server-revocable sessions, quotas and owner-scoped REST/AI/cache/export boundaries. Staging uses passcode mode; production email configuration remains open. |
| AI | Chat tools read current records; chat has frame/history/message/turn limits; websocket inbox is bounded. Insights validate generated payloads, cache by fingerprint/model, and fall back to rules. | Fake-provider tests do not prove model availability, factual quality, privacy guarantees, or production provider integration. |
| Runtime safety | Public health in `main.py` now logs database failures privately and returns sanitized HTTP 503. API responses are no-store, unknown API paths return 404 instead of SPA HTML, and injected app database factories apply to REST. | Duplicate shadowed health/version handlers were removed; the public handlers are the sole definitions. |
| Frontend reliability | Attendance captures section/day in mutation variables; reports bound extra-credit bar width; chat detaches stale socket handlers and bounds stored conversation history. Focus, mobile styles, and reduced-motion CSS exist. | Component regressions cover concurrent writes and private-session boundaries. Chromium browser workflow and WCAG checks are being verified; full screen-reader and production-release coverage remains open. |
| Migrations | Alembic baseline `0001` and startup upgrade path exist. `tests/test_migrations.py` checks schema shape, metadata drift, repeat startup, and legacy data preservation. | Native chain is 0001 -> 0002 -> 0003. Independently published accounts0002 needs the explicit offline adoption bridge; it is separate from legacy EduTrack conversion. |
| Delivery | Exact-source CI covers Python, strict frontend checks, browser workflows and restricted-directory Docker/auth smoke. Deployment binds an immutable digest and fresh isolated replica. | Source07974de passed all gates:1294API/no skippedxfail,194web,4browser,83E2E. Staging00005-klh serves it; synthetic HTTP and independent restore/readback passed; integrity/FKs/head0003 and raw history preserved. Production domain remains legacy. |

## Public deployment evidence

The coordinating agent reports a direct HTTP observation that the public site index is served while `/api/health` returns 404. Treat this as an unresolved deployment/API routing mismatch. It does not establish which commit is deployed, whether another backend path exists, whether production authentication works, or whether production records persist. Do not infer that local changes have reached production.

Acceptance evidence: record release/image identifier, host and observation time, public health/version responses, protected API denial without a session, authenticated read behavior, frontend deep-link rendering, WebSocket handshake/streaming, and persistence after replacement of the running instance. Use synthetic data for write-path checks.

## Prioritized remaining requirements

Priority 0 means a release integrity or data safety prerequisite. Priority 1 means a core overhaul capability. Priority 2 means subsequent depth and polish. Each row remains open until its acceptance evidence is attached.

| Priority / area | Concrete requirement and observed reason | Evidence needed to close |
| --- | --- | --- |
| P0 — deployment | Identify and repair the public frontend/backend routing and release mismatch before claiming a deployed improvement. | Versioned artifact and full public-host smoke evidence listed above. |
| P0 — persistence | The accepted ADR selects a single-writer Litestream pilot. Startup accepts Cloud Run SQLite only after validated entrypoint restore. Isolated replica restore passed; production schema adoption, final drain, retained data import and cutover remain open. Cloud SQL is optional. | Reviewed infrastructure/configuration, data survives a new revision/instance, backup and restore into an isolated environment, documented recovery steps. |
| P0 — reproducible delivery | Keep package manifests, lockfile, installed dependencies, Docker toolchain, CI and local commands consistent during the dependency upgrade. Finish strict TypeScript validation and all relevant gates. | Clean `npm ci`, typecheck, lint, tests, production build and Docker build using committed lockfile; Python lint/format/tests; CI results for the exact revision. |
| P0 — migration adoption | Validate legacy schema before stamping `0001`. Implemented schema comparison rejects partial/incompatible legacy databases before stamping; adoption now uses fixed baseline validation. SQLite snapshot/recovery tests preserve all app records in a new database; real production restore rehearsal remains open. | Complete legacy adoption succeeds; partial/incompatible legacy databases fail clearly without mutation; real schema upgrade preserves representative records; restore rehearsal. |
| P0 — privacy | Define permitted student data sent to the model, retained in browser storage, and logged. Parent-draft context now excludes confidential notes entirely; broader chat/insight and retention policy remains to be defined. | Documented policy, data-minimization implementation, adversarial tests for private-note disclosure and cross-student output, browser logout clearing verified. |
| P1 — identities and access | Decide single-teacher versus multiple-teacher/school product behavior. For shared use, introduce users/roles and owner/organization scoping across REST, CSV, AI tools, cache keys, and WebSocket context. Owner relationships, email accounts and scoped authorization are implemented; deployed email policy/owner mapping remains open. | Migration plus negative authorization tests for every record surface; account/session lifecycle demonstrated in browser; isolated teacher datasets. |
| P1 — model integrity | Database-enforced grade-level/points/max-points/enum invariants are implemented and tested. Define assessment edits, enrollment/transfer history, academic terms, archive/delete behavior, and note management. Transfers now preserve old scores/history and exclude old-section scores from active metrics; academic terms, archive policy and dated enrollment remain open. | Reviewed migration and data-policy decisions, direct invalid database writes rejected, preserved transfer/history examples, CRUD integration tests and UI workflows. |
| P1 — grading policy | Make weights, grade thresholds, missing-work treatment, extra credit, attendance scope and reporting periods explicit and configurable at the appropriate level. Current weights/thresholds are module constants. | Hand-computed fixtures prove each configured policy across overview, roster, detail, reports and AI; future/due work and extra credit handled consistently. |
| P1 — concurrent writes | Prevent old grade/attendance requests from overwriting newer intent and provide visible pending/success/error states. Client rollback alone cannot enforce ordering of server commits. | Deliberately reordered requests and failed saves preserve the latest intended state; switching section/day/student cannot apply stale results to a different record. |
| P1 — backend scale | Introduce bounded pagination/filtering where appropriate and measure representative large datasets. Summary history and AI tool candidates are bounded/streamed; true API pagination, broad export bounds and representative production capacity remain open. | Dataset/load definition, latency/memory/query-count measurements, pagination contract and UI, scoped tool queries, no regressions in computed metrics. |
| P1 — AI reliability | Unify provider-client lifetime, explicit timeout/retry rules, structured output validation and cancellation across chat, insight and parent updates. Chat, insights and parent drafts now close provider clients; parent drafts have a 30-second SDK timeout and 45-second total deadline. All three workloads share a bounded provider budget and total deadlines; real-provider evaluation and cross-worker admission policy remain open. | Fake and real-provider smoke tests, provider failures/timeouts, concurrent calls, cancellation, fallback provenance and no leaked resources. |
| P1 — AI grounding | Apply the same untrusted-text hygiene to parent updates as chat/insights. Parent-update context now sanitizes and bounds names/titles in a separate student-record block and omits notes. Adversarial regression tests exist; factuality and privacy evaluation remain open. Add evaluated factuality and privacy checks rather than relying on prompt wording. | Malicious delimiter/instruction fixtures stay data; drafts cannot cite other students or disclose private notes; benchmark questions compare statements with underlying records. |
| P1 — AI usefulness | Build reviewable teaching actions from insight/chat findings: concrete intervention plans with supporting records and teacher confirmation before any persistent action. Current tools are read-only searches/statistics. | Representative teacher tasks produce traceable evidence and editable actions; stale data is identified; any future writes require explicit user intent and authorization. |
| P1 — frontend overhaul | Validate and improve navigation, class onboarding, empty/error states, reporting, charts, grade entry, roster management and assistant behavior on desktop/mobile. A file conversion is insufficient product evidence. | Browser walkthroughs with no console errors at representative viewport sizes, keyboard-only workflows, clear loading/retry/save feedback, screenshots tied to the exact release. |
| P1 — accessibility | Audit modal focus, assistant focus/escape behavior, table navigation, status announcements, form errors, contrast and chart alternatives. CSS focus/media rules alone do not prove access. | Automated accessibility checks plus manual keyboard/screen-reader walkthroughs, including failed saves and streaming replies. |
| P1 — end-to-end coverage | Add browser integration checks spanning authentication, course/section creation, roster import, student edits, gradebook, attendance, reports and AI fallback. Current frontend tests exercise individual components; Docker smoke tests are narrow. | Browser tests use an isolated backend/database and verify persisted results across reloads and logout/login. |
| P2 — operations | Add actionable request/error/provider metrics, correlation identifiers, bounded logs, readiness/liveness distinctions and release rollback guidance; scale throttles/session policy to the chosen deployment. | Sanitized operational output, simulated failures detected, readiness behavior tested, rollback and restore practiced. |
| P2 — report depth | Add period comparisons, class-average overlays, trend series and clearer metric explanations; ensure exports and parent drafts share the same reporting window. | Hand-computed period fixtures and browser comparisons, accessible visualizations, clear missing-data behavior. |

## Verification ledger

The coordinating agent owns final integration validation. Add exact commands, revision/artifact identifiers, terminal results, and relevant limitations here as checks complete. Do not convert “test exists” into “test passes.”

- Python: `ruff check .`, `ruff format --check .`, `python -m pytest`.
- Frontend: clean install, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
- Container: image build, authenticated/unauthenticated smoke tests, unhealthy database behavior, static routes and startup rejection without credentials.
- Data: migration drift/adoption checks, backup/restore, concurrency tests and persistence across replacement.
- Product: browser workflows, mobile/keyboard/accessibility checks and provider integration using synthetic records.
- Production: public routing/release identification, protected API, WebSocket and durable storage evidence.

Source anchors: `superteacher/{main,auth,config,db,models,metrics,queries,ai,ai_tools,reports,schemas}.py`, `superteacher/routers/`, `alembic/versions/`, `web/src/`, `web/{package.json,package-lock.json,tsconfig.json,vite.config.ts}`, `.github/workflows/ci.yml`, `Dockerfile`, `cloudbuild.yaml`, `deployment_tests.py`, `tests/`, and `docs/DEPLOYMENT.md`.

### Integrated checks completed in this milestone

- Python 3.12: `AUTH_DISABLED=true /tmp/superteacher-backend312/bin/pytest -q` passed **136 tests**; Ruff lint and format checks passed. AI tests use fake providers.
- Clean Linux container web stage: `npm ci` during image build, strict typecheck and Vite build passed; `npm run lint` and `npm test` passed **44 tests across 6 files**.
- `docker build -t superteacher:overhaul-review .` passed with Node 24.20.0. Container smoke verified health 200, protected overview 401, unknown API JSON 404, root/deep-link HTML 200, and startup rejection without a password. This is local verification, not deployment.
- Chrome isolated context against local container verified passcode login, course creation, synthetic student creation, roster rendering, attendance page, and successful attendance marking. Initial unauthenticated auth probe generated an expected 401 console resource message; no broader console/accessibility claim is made.
- Production read-only observation: host index returned 200 and `/api/health` returned 404. No production writes or deployment were performed.
- Shared Graphify source refresh requested; final completion must be checked from the running refresh handle. Graph corpus has no useful Super Teacher source coverage. Agent Hub context did not provide a repository handoff.

The full objective remains active: durable deployment, identity/authorization design, schema/business-policy evolution, complete browser/mobile/accessibility checks, workload scaling, evaluated AI quality, and production release evidence are still outstanding.

Continuity note: Agent Hub checkpoint rejected this repository as having no configured memory scope. This file is the local verified handoff. Graphify refresh shell session `66755` remained live at last poll; do not restart solely because observation timed out.

### Second integrated milestone

- `AUTH_DISABLED=true ST_TEST_POSTGRES_URL=<isolated local PostgreSQL> /tmp/superteacher-backend312/bin/pytest -q`: **200 passed** including PostgreSQL integration; Ruff lint/format and whitespace checks passed.
- Strict TypeScript now includes every browser test and setup file; no JavaScript/JSX remains under `web/src`. Clean Linux Docker web stage build/typecheck passed; final full frontend suite passed **64 tests** across eight files after nested-dialog cleanup and notification regressions.
- PostgreSQL 17 acceptance checks cover initial/repeated migrations, persisted records after reconnect, invalid grades and nonfinite scores, and valid extra credit. A separate authenticated application-container smoke created course/section/student rows and verified the student survived replacing the application container.
- Cloud Run deployment configuration uses an immutable build image tag/version, explicit Cloud SQL instance, and database URL secret. Resources are not provisioned and existing production data is not migrated. The app rejects local SQLite when K_SERVICE identifies Cloud Run; SQLite remains supported on a persistent local Docker volume.
- SQLite operator command supports validated online backups and new-path recovery without replacing existing files. Nineteen tests cover relational records, active WAL writers, output permissions, corrupt databases, destination races, read-only access and failure cleanup.
- AI chat/insight/draft admission is shared and bounded per worker, with deadlines covering retries/tool rounds. Cancellation closes clients and releases capacity; final insight waiter cancellation stops deduplicated generation. Saturated insight/draft paths use provenance-labelled fallbacks.
- Authentication clears private state immediately on expiry/logout, ignores superseded session checks, waits for logout completion before another login, and rotates QueryClient so late mutation writes target a discarded cache. Five regression cases cover these boundaries.
- Shared UI uses modal portals, reference-counted inert background and scroll locks, focus containment/restoration, fixed mobile chat overlay, reachable mobile account/theme controls, accessible daily attendance table, and persistent error notifications. Targeted regressions passed; a complete browser/screen-reader audit remains open.

Teacher-account and final storage preferences were requested asynchronously; no answer has been received. PostgreSQL is prepared as a hosted option while SQLite remains supported locally. Identity/tenancy implementation awaits that direction; independent work continues within the overhaul.

Final local checks: PostgreSQL-backed app data survived replacement of the application container. Final lint/typecheck/build and 64 frontend tests passed. Isolated test containers and network were removed. Latest shared refresh requested in shell session `50929`; previous refresh `66755` is also live. Do not restart due solely to silent observation intervals.


### Third integrated milestone

- Assessments now support editing title, type, due date and maximum points while preserving raw scores; the UI explains percentage recalculation. Private notes support scoped editing and confirmed deletion. API and component regressions cover wrong-resource access, invalid values, failed writes and cache refresh.
- Section moves now preserve all prior score rows, including zero and NULL. Active metrics, detail scores and AI summaries use only the current section. A scoped plain-column history endpoint and profile history table expose prior work; moving back restores previous scores and fills assignments added while away. Full dated enrollment/term history and immutable assessment snapshots remain absent.
- AI tools now filter metadata before reading history, stream summaries in 200-student batches, retain at most 25 ranked results, and scope focused history/notes. Chat roster snapshots consume aggregate-only batches, retain bounded rendered rows, and cap focused work context at 30 recent records. Existing full-list API responses remain unpaginated.
- Future attendance no longer affects present-day metrics; explicit historical cutoffs work in both ORM and column paths. Future ungraded assignments are labelled NOT YET DUE with dates in AI records and parent-draft context.
- Synthetic benchmark with 1,000 students, 40,000 scores and 60,000 attendance records showed focused lookup 4.931s/113.23 MiB to 0.028s/0.28 MiB; whole-class tools retained about 4 MiB versus 113 MiB. These tracemalloc-local measurements are not production guarantees. Reproduction and equality checks: `docs/PERFORMANCE.md`.
- Offline AI grounding evaluation uses hand-calculated synthetic records, malicious text and private-note fixtures. 29 cases pass. Provider doubles test transport/structure, not real-provider factual accuracy or prompt-injection resistance. Semantically false but schema-valid provider claims remain possible. See `docs/AI_EVALUATION.md`.
- Playwright production-build browser harness uses a temporary SQLite database, explicit test credentials, disabled paid AI, cleared inherited settings and no deployment .env. CI now gates Docker on Chromium workflows; failure artifacts are ignored locally and retained in CI for seven days. See `docs/E2E.md`.
- Clean Linux Docker web stage strict typecheck/build, ESLint and 71 frontend unit tests pass. Runtime image rebuilt successfully; public health 200, protected overview 401 and SPA deep link 200 verified locally. The integrated PostgreSQL 17 suite passed 277 tests before subsequent proxy/transfer work; final transfer-integrated suite is being observed.

Continuity: final browser workflows and final backend suite are still being observed. Teacher identities/tenancy, hosted database provisioning/cutover, public-host release/routing, real-provider evaluation, report-period/grading policy, pagination, grade-preserving transfers and broader manual accessibility remain open. No production deployment or production data changes were made.


### Release investigation and expanded product work

- Final pre-transfer checks: 277 backend tests with PostgreSQL 17, 77 frontend tests, three Chromium workflows, strict TypeScript/build, ESLint, Ruff and runtime-image checks passed. Proxy regression suite then passed 24 tests including three new transport cases. Cloud Run configuration supplies forwarded-header trust specifically at the platform; local Docker retains restricted defaults.
- Student profile edits and roster pagination were added. Search/sort cover the entire loaded roster while at most 50 rows are rendered; REST list responses remain unpaginated. Previous-section history also renders bounded tables and rejects mismatched/stale profile responses. Full current frontend suite passes 83 tests.
- Expanded Chromium CSV import/read retry/mobile/auth workflows pass. Fault injection found a real failed-score rollback bug: a rejection read its own optimistic prop. ScoreCell now restores its pre-save captured value while preserving later edits; focused regression suite passes. Full browser suite is being rerun with this correction and grade-preserving transfers.
- Read-only cloud inventory identified the routing mismatch: both custom domains map to legacy `edutrack` (`edutrack-00018-t58`, `edutrack:v0.1.0`) in `portfolio-383615/us-central1`; newer `superteacher` (`superteacher-00002-b5n`, image/version `c344911`) is a separate healthy direct service. No live traffic/configuration/data changes were made. See `docs/RELEASE_PLAN.md`.
- The newer direct service has no DATABASE_URL, Cloud SQL attachment or mounted volume; its source defaults to SQLite. The project inventory returned no Cloud SQL instances. Avoid replacing the service until existing-record retention and durable cutover are resolved.
- `infra/cloud-sql` is a concrete unapplied PostgreSQL17 infrastructure configuration with backups/PITR, deletion protection, enforced connector networking, explicit runtime identity and a database URL secret. Terraform formatting/validation passed with Terraform1.13.5 and signed locked Google provider7.46.1. Write-only provider fields and ephemeral password avoid credentials in Terraform state. Budget/HA, state backend, runtime identity, SQL privilege hardening and import/restore decisions remain open; no resources or Terraform plan were applied. See `docs/CLOUD_SQL_PLAN.md`.
- Build contexts exclude Terraform state/work, browser traces/screenshots, SQLite WAL/backup artifacts and generated design-tool context. An untracked `.superdesign` folder appeared from another harness; its source/tools were not edited. Application Ruff checks exclude that generated context explicitly; do not discard concurrent work.

Next verification: final PostgreSQL-backed backend suite, fresh Docker production build, four expanded Chromium workflows including fault rollback and grade transfers, aggregate source refresh. Next substantive scope: private teacher identity/ownership, report/academic-term/timezone policy, real-provider evaluation, reviewed durable provisioning/data migration and public cutover. The full overhaul goal remains active.

### School calendar integration checkpoint (2026-10-01)

- `SCHOOL_TIMEZONE` now validates an IANA zone (default UTC). HTTP requests capture one school date; websocket connections retain the configured zone and obtain a new date for subsequent operations. Authenticated `/api/calendar`, student-detail `as_of`, and class-summary `as_of` make the cutoff explicit. ORM/schema defaults, current attendance, metrics, AI records and insight fingerprints use this date. Historical overrides remain supported. Cloud Build accepts `_SCHOOL_TIMEZONE`.
- Attendance defaults and new-assignment due dates now use the API school date. Manual attendance date selection survives calendar refresh. Student assignment rows distinguish future ungraded work from missing work using the response cutoff. Assignment creation accepts positive fractional maxima and holds the dialog during writes.
- Focused frontend typecheck and lint passed. Five focused test files had 18 passing cases and one test waiting on an unrelated permanent toast alert; correcting that assertion produced four passing calendar cases, completing all 19 focused cases across the runs. These focused checks do not establish full-suite completion.
- Fresh four-workflow browser baseline passed three workflows and found an axe link-in-text-block failure on the empty assignment message after a transfer. Paragraph links now have underlines; the final browser rerun remains pending. Successful baseline steps included failed-score rollback, durable raw-score edits, notes, transfer history, login/logout/expiry, import/retry and mobile keyboard behavior.
- Python lint, formatting and compilation passed after calendar integration. Calendar/grounding runtime checks were not executed: the shared heavy-check queue timed out with exit 75. No lock bypass or unchanged retry was performed. Other harnesses are running checks in sibling worktrees; the single browser verification owner will wait for available resources before integrated broad checks.
- Independent live-source review found a chat-turn midnight snapshot/tool mismatch; a per-turn freeze fix and dedicated regression are being implemented. This checkpoint does not claim that fix is verified yet.
- Agent Hub still returns no selected project context for this actual repository; this file remains the local handoff. Graphify query again lacks Super Teacher code coverage, so live source was used. A shared aggregate refresh is being observed. Prior shell handles recorded above are historical and do not identify current jobs after runtime replacement.

Next: integrate the chat boundary fix; final settled backend/PostgreSQL and frontend/browser/package checks under the shared resource lock; record actual results and cleanup. The original overhaul goal remains active, including teacher identity/ownership, hosted data retention and cutover, academic-term/grading policy, pagination and real-provider evaluation. No production changes were made.

Checkpoint follow-up: the per-turn chat freeze is integrated. The new real-websocket/fake-provider regression passed (1 case, 1.11s), including threaded dispatch across midnight and rollover on the next turn. The changed single ORM-default/historical-cutoff integration case passed (1 case, 0.85s). These were lightweight focused iteration, not a rerun of the previously lock-blocked combined suite. Student profile trend and attendance charts now exclude future raw rows from current-day visuals; a strengthened frontend regression is being checked. Global broad verification remains unqueued while another harness holds the shared lock; sibling Super Teacher benchmark waiters were observed and left untouched.

Latest source validation: refreshed student chart cutoff regression passed all four SchoolCalendar cases (1.72s); strict TypeScript and ESLint passed. Python Ruff and formatting passed across 54 files; whitespace checks passed. Agent Hub checkpoint again rejected this repository because it has no configured memory scope, so this document is the saved handoff. Current shared Graphify refresh is shell session `7016` (PID613474 at observation), still awaiting completion; do not start another refresh due to silent output. Existing unrelated refresh jobs were observed and not disturbed. Final integrated broad checks have not been queued while the lock holder's E2E run and other waiters remain active. Browser verification owner is `/root/browser_verify_resume`; no additional browser page/window was opened in this continuation.

### Native workspace reliability integration

The authoritative checkout is now `/home/jkail/projects/superteacher`; the Windows original remains separate. Source and focused checks below use the native checkout. Previous agent sessions are no longer live; their partial source was inspected before being completed. Current root is the sole integrated verification owner.

- New-course onboarding now creates the course and its optional initial section in one transaction (`CourseIn.initial_section_name`); failed section creation leaves neither record, and retry works. Bare course creation retains its existing contract. Five focused backend cases passed.
- Roster dialogs capture immutable write payloads, guard repeated submits and pending close paths, validate trimmed names and freeze input during writes. CSV import guards asynchronous file races, manual edits, unmount, read failures and stale result messages. Nine focused component cases passed after test live-region queries were scoped to the dialog. TypeScript and ESLint passed.
- Assignment maximum edits validate every preserved score, including transferred and future work, before changing metadata. A finite raw score divided by a tiny positive maximum previously committed nonfinite percentages, producing contradictory null JSON averages/A grades and CSV/template `inf`. Unsafe edits now return 422 without changing fields, scores or fingerprints. Finite extra credit and positive fractional maxima remain supported. CSV raw scores/maxima preserve fractional precision while integer formatting stays compatible. The combined numeric/report/assessment-edit check passed 53 cases after calendar fixtures were aligned with `school_today()` rather than the machine-local date.
- API requests now capture a session generation. Late 401 responses from an earlier session cannot sign out a newly authenticated session; current-session expiry still clears private UI. The real-transport regression plus existing auth/API tests passed 15 cases.
- Required native knowledge workflow was read. Linear/vault tools are unavailable and Agent Hub cannot identify this repository's memory scope; no external issue/note writes were made. This file remains the curated local checkpoint. Shared Graphify queries still lack Super Teacher source coverage and refer to the original shared corpus; current native source was inspected directly. Older refresh shell session7016 is now missing and must not be treated as live or as proof of indexing.

Final native broad check is prepared in `/tmp/st-native-verify.sh`, with output `/tmp/st-native-verify.log`. It runs sequential backend/PostgreSQL17, lint/format, frontend unit tests (two workers), strict production build, four Chromium workflows (one worker/one page at a time in an isolated container), then Docker packaging. Disposable PostgreSQL/browser containers are created only after obtaining the shared lock and cleaned by the script trap; no production data, public traffic or other agent's server is used. Foreground wrapper shell session67718 is currently waiting for the shared lock. A sibling Super Teacher scale benchmark holds the lock (PID2260994 at observation); no repeated check was started. Poll that existing handle and record its terminal result before deciding the next action.

The full original overhaul goal remains active. Teacher identity/ownership, hosted data retention/provisioning/cutover, academic terms/grading policy, true API pagination, real-provider evaluation and broad release evidence remain open. A separate accounts worktree has concurrent uncommitted work; it was inspected read-only and not merged or overwritten.

Native integrated check terminal result: foreground wrapper shell67718 exited **75** before obtaining the shared lock; `/tmp/st-native-verify.log` is empty because no test/container/build command started. No retry or bypass was performed. Lock holder2260994 was confirmed live in the sibling `st-scale` worktree running a 5,000-student AI benchmark (five measured runs/one warmup) when the wait ended. All disposable verification resources therefore remain uncreated. Root started shared Graphify refresh shell69229 after settled source edits; initial output synchronized portfolio, blackbox and encore, which does not establish native Super Teacher coverage. Poll that existing refresh handle rather than starting another.

Read-only identity candidate review is now saved in `docs/IDENTITY_INTEGRATION.md`. The independent accounts candidate cannot be merged wholesale: its `0002` migration collides with native integrity `0002`, transfer code deletes preserved grade history, browser authentication remains the old passcode JSX flow, and established chat connections do not recheck revoked sessions. The document gives source-qualified owner-scoping, migration/adoption, mail/privacy, origin, concurrency and browser requirements. Candidate files were neither edited nor merged; its checks do not establish native completion. The shared heavy lock later moved to a live 20,000-student scale benchmark in the sibling worktree; final native verification is still blocked and has not been retried.

Shared Graphify refresh shell69229 completed successfully (exit0), publishing164478 nodes to `/home/jkail/projects/graphify-out/graph.json`. Its synchronization/extraction covers portfolio, blackbox, encore and agent-hub plus existing evidence layers; this is not proof that native Super Teacher code is indexed. Direct source inspection remains required for this repository.

AI configuration review: official Anthropic model documentation currently lists both native default model IDs, so no speculative model change was made. A presence-only native settings check found no AI provider credential; real-provider quality remains unverified. See `docs/AI_EVALUATION.md` for the source and limitation. No model requests or production secret retrieval were performed.

## Native merge and release continuation (2026-10-02 UTC)

- Native overhaul snapshot `c69c30f` was committed and pushed to `claude/upbeat-volta-k9dtci` before integrating `origin/main` `ce94d50`.
- Team resolved current security, observability, Litestream/GCS persistence and independent browser-suite changes with the native TypeScript/calendar/bounded AI/grade-history implementation. Strict scheme/host/port origin checking remains; Cloud Run explicitly trusts its platform proxy. Untrusted forwarded headers do not bypass origin checking.
- Managed Cloud Run SQLite now requires the entrypoint's successful restore marker, a GCS URI and matching absolute database file. Ephemeral SQLite remains refused. The entrypoint clears inherited markers before restore. Cloud Build builds an immutable image only; staging skips invocation/healthcheck, and promotion requires confirmed drain of the current writer. Schema-aware backup/rollback remains required.
- Verified focused merged checks: 33 authentication/storage cases; 37 selected serving/security cases; 4 CSV cases; AI owner reports 152 initial passing cases (48 stale incoming prompt assertions failed), then 12 representative adapted prompt/instrumentation cases passed. Full merged suite is not yet proved. Ruff check/format passed for tracked Python source. External `.superdesign` context stays untracked and excluded from lint/build inputs.
- Current live metadata changed during this work: separate `superteacher` service serves the same `ce94d50` image through revision `superteacher-00005-bmx`, with a DRILL environment name and one observed idle runtime. This suggests an external recovery drill; owner identity is unverified. Custom domains still map to legacy `edutrack`. Do not overlap traffic changes with another deployment owner or infer drained writers from traffic0/app-exit logs.
- Drain proof: manually disable the service, remove invocation tags, then require post-disable explicit active+idle zero instance counts for every writer-capable revision after metric latency; missing series is not proof. Preserve a restore point before schema0002. Stage candidate against an isolated replica prefix first.
- Next: publish the merged PR, collect exact-commit CI gates, fix failures, build/deploy an isolated candidate, prove authenticated image workflows and restart/restore, then coordinate production drain and migration-safe promotion. Identity candidate PR12 and scale PR11 remain independent work; do not lose native privacy, calendar or grade-history guarantees when integrating them.

### Exact-commit CI and scale integration

PR15 https://github.com/jckail/superteacher/pull/15 opened for0344284. CI36967196648 passed lint, frontend unit/type/build and native browser workflows. Backend recorded774passed,9failed,1xfailed; incoming E2E recorded28passed,4failed,49notrun. Failures were stale expectations: lowercase404message, permissive cross-scheme origins, old vite.config.js, unhealthy200, unbounded/malformed passcode401, selectors matching neweditcontrols, removed environment-variable product text, and two focus expected-failures now passing. Team retained assertions, adapted contracts and added both-direction origin rejection;11targeted backend cases passed. Changes committed27eb8ae.

External main advanced6214af9 by merging scalePR11 during this work. Integrated its report score map and indexed attendance ordering, preserved native measured performance with incoming findings labeled historical, adapted fake section/calendar fields, and replaced constant-query/obsoleteAIxfails with bounded-batch/history guards. Added1k report lookup regression and transfer/future-work/calendar cases. Team verified39focused cases in4.02s; root Ruff check/format passes100files. Docker CI now also verifies readiness, real login, authenticated overview/calendar and logout. Incoming1kbenchmark artifact job is informational. Next new exact-commit CI must prove all release gates before image/deployment.

CI36967844593 forbf7aca1: **822backendpassed,1xfailed**; lint, webunit/type/build and informational1kbenchmark passed. Nativebrowser3passed/1failed: axe caught mid-animationtoastcolorcontrast; retry selected another course's same-labelPeriod2. Toast entrance now retains opacity; retryfixtures use UUIDs and sectionIDs. IncomingE2E78passed/3failed: mobilechat correctly exposes modal dialog instead of desktop complementary region; tests now assert dialog+aria-modal onphones with allaxe assertions retained. Friendly chat fallback explains remaining classroom tools without exposing environment-variable setup. Exact new CI required beforedeploy; Docker was gated/skipped on the failingbrowserrun.

CI36968302956 forda86cee: incoming E2E81passed; lint/web/benchmark passed. Backend821passed/1failed/1xfailed because root missed older `test_chat.py` fallback-key assertion; corrected meaningful teacher notice + noenvironmentsetup assertion,2focusedcasespass. Nativebrowser3passed/1failed because longUUIDcoursename widened native ScopePickerselect onmobile; team bounded flex/selectwidths, retainslongfixture andoverflowassertion. ProtectedCloudBuild session28412 endedexit75 with emptylog—no cloud command/archive/image/deployment began. Do not retry unchanged merely because lock isbusy. `/tmp/st-stage-candidate.py` is prepared,notexecuted; use only an exactCI-verified image andisolated replica prefix. Externalpersist deployment job observed active; do not overlapproductiontrafficownership.

Externalmain advanceddae26a5 with passwordlessaccounts PR12. Nativebranch must integrate it beforemerge/release, preserving TypeScript, numericconstraints, calendar, bounded AI, active-sectionmetrics, parentnoteprivacy andretainedtransferhistory. Identitymigrationrevisioncollision andownership for newlyaddedroutes remain concrete integration requirements; avoid wholesaleacceptance of olderJS/routes. Rootcontinues teamintegration within original activegoal.


### Native accounts integration checkpoint

The main merge (`dae26a5`) is resolved with native integrity migration `0002`
retained and accounts assigned successor `0003`. Startup and Alembic CLI reject
ambiguous independently published accounts-`0002` databases before DDL. A validated
backup/clone adoption bridge is being implemented before using the integrated image
against such a production replica.

The team ported accounts into TypeScript; scoped native edits, transfers, history,
calendar, reports and AI by owner; preserved raw grades and bounded queries;
made signup/starter and quota claims transactional; and revalidated sessions
without extending idle expiry through watcher polls. Root verified 11 selected
tenancy/storage/migration cases and 13 auth/token cases. Team evidence: 10 frontend
accounts, 29 account concurrency/lifecycle/export/mailer, two idle-session and
10 AI/calendar/chat cases passed. WebSocket cleanup is being fixed. Full combined
CI and isolated candidate deployment remain pending.

Agent Hub was invoked with the actual native repository but still reports no
selected/configured project. This local ledger is the continuity fallback.
Graphify refresh completed but the shared corpus still lacks Superteacher coverage;
current source inspection remains necessary. No unrelated browser tabs/processes
were changed. The original goal remains active, including deployment, production
email, academic terms/policy, pagination and real-provider evaluation.

Integration follow-up: all 81 selected numeric/transfer/calendar/tenancy cases are
covered by passing focused runs. Trusted-proxy cookie tests passed 28 cases with
one known stateless-passcode logout xfail; explicit-cookie and concurrent per-email
limit regressions each passed. The real WebSocket context-exit cancellation defect
was fixed by shielding final draining of owned tasks, preserving lease/generator
cleanup. Four unchanged auth/revocation/calendar cases passed; the two auth cases
also passed their focused verification rerun. Root lint/format and diff checks
pass before the merge commit. Full combined CI remains the release gate.


CI36970357403 for `948b998`: lint, frontend unit/type/build, native browser,
incoming E2E and informational benchmark passed. API: 883 passed, 40 failed,
29 fixture errors, one known xfail. Many native direct ORM/raw SQL fixtures omitted
new owner records/columns; incoming quota fakes conflicted with API-key admission.
New routes require explicit cross-tenant attack inventory. Team fixes preserve
strict production constraints. Root found and fixed aggregate overflow from
adding multiple finite near-limit raw scores before normalization; the new
extreme-score read/export regression and focused API validation passed 11 cases.
Docker remained gated. A new exact-head run is required.

Offline accounts snapshot adoption is implemented with exact legacy schema and
independent native-chain proof, lossless row hashes, private clone migration,
integrity/FK checks and atomic no-overwrite publication. Twelve focused tests
passed. No production snapshot was fetched or replaced; production adoption,
isolated candidate restoration, writer-drain and domain cutover remain pending.

CI-fix verification: 26 numeric/metric cases passed after the linear-time safe
aggregation fix; 19 backup cases, nine scale/tenant attack cases, 45 quota/grounding
cases and 13 tool-scale cases passed. The new candidate script records synthetic
writes in a private receipt and supports readback after a separate isolated restore.
Its syntax/contract checks do not establish a deployment; no live run occurred.


### Verified merge and isolated staging release

PR15 merged as8ceb050 after all six required CI gates passed for7166813; API963
passed/oneknownxfail. Merged-main CI36971521702 also passed. CloudBuild8e3a2ff4
succeeded and its immutable digest was deployed as isolated staging00001-7kx.
Health/readiness/auth/calendar/version/SPA/logout and synthetic CRUD/precise extra
credit/transfer history/active metrics all passed. Exact artifact, URL, version map
and private receipt locations are recorded in DEPLOYMENT_STATUS.md. Public domain
still reportsv0.1.0; existing direct service remainsdae26a5. No productioncutover.

Bugbot's FK/autobegin warning was reproduced as a false positive: SQLAlchemy
logical transactions differ from SQLite physical transactions for PRAGMA reads.
Nine focused physical-transaction/file-preservation/startup/CLI cases passed;
runtime source was unchanged. Added regression coverage is being committed with
this evidence. Operator-endpoint review found no global backup/seed/reset/debug
HTTP routes; accounts cannot access global metrics without the operator bearer.
Five focused route/export/metrics cases and transient accounts probes passed.

Remaining release work: inspect the existing recovery-only execution (do not
launch duplicate retries), verify replica-restored synthetic records, obtain and
validate a private consistent production backup/adopted copy, coordinate writer
drain, preserve legacy domain data, and perform the final domain cutover. Production
passwordless email/provider/owner settings, least-privilege runtime identity,
academic terms/grading policy, true API pagination, bounded large exports and
real-provider evaluation remain open under the original active overhaul goal.

Staged replica recovery succeeded in execution9jlsw: integrity/FKs/native0003,
synthetic transfer metadata and exact grades all verified in a fresh copy.
Subsequent candidate receipt readback passed. Production-copy adoption rehearsal
execution5wggt is pending; it is read/restore/clone-only, with no serving writes.

Production-copy rehearsal failed closed: first restored sidecars were correctly
refused; a diagnosed preparation fix uses validated standalone backup. Second
executionvtgs9 then found genuine schema drift against exact publishedaccounts0002.
Live DB remained unchanged; schema-only diagnosis is next, before extending mapping.
Legacy API archive saved privately outsideGit, mode0600 in0700directory; shape,
identity/reference and repeated-payload checks passed. It is non-atomic and cannot
prove complete legacyDB preservation. LEGACY_CUTOVER.md records the artifact and
faithful importer/rollback prerequisites. Preserve records by default; do not infer
no user data from demo seeding. No production/domain cutover was attempted.

Schema-only diagnosticmnl7l identified only the two pinned Litestream bookkeeping
tables; application/account schema matchedpublished0002. The bridge now validates
both exact internal DDLs and preserves their rows, with no prefix-based exemption.
Twenty focused tests passed including real pinned local replication/backup/adoption.
Missingpair/column/index/trigger/STRICT drift rejects. Latestmain66ad6bb CI36973071658
passed all gates:968backendpassed,1knownxfail. New helper-source fix needs its own
CI/image/rehearsal before deployment; staging7166813 remains verified/unchanged.

Continuation checkpoint: source9de97ce was committed/pushed to main and
CI36974717368 passed every release gate, with976APIpassed/1knownlegacylogoutxfail.
The protected CloudBuild attempt for9de97ce stopped at shared-lock exit75 before
any cloudcommand/archive/build began; `/tmp/st-cloud-build-9de97ce.log` preserves
the blocker. No unchanged retry or lock bypass. Staging still serves verified7166813.
The private legacy API archive now also has a no-overwrite versioned GCS copy;
downloaded-byte SHA256 matched. Its non-atomic capture limitations remain.
The corrected accounts helper needs an image and real production-copy rehearsal;
faithful legacy import, authoritative dataset, rollback, writer drain and domain
cutover remain open. A team audit confirmed live-prefix staging could start a
second replica writer upon invocation. The helper now requires explicit service
and prefix, tightly scoped isolation acknowledgment or observed drain, and a
post-build drain recheck. Promotion binds the actual candidate replica URL to
the supplied prefix. All25focused mocked-cloud tests passed; current staging
revision metadata independently confirmed the real projection shape without
printing environment values. `LEGACY_IMPORT_PLAN.md` records faithful roster
mapping and historical fields that cannot become dated events. No production
traffic/domain/schema change was made.

Final release checkpoint:5113de8 pushed to main; CI36978867068 all gates passed,
996APIpassed/1knownlegacy-passcode-logoutxfail. Shared Graphify refresh completed
and published164478nodes; native Superteacher coverage remains absent, so source
inspection is authoritative. Corrected9de helper artifact was independently
hash-bound to the immutable716runtime and all six support files; recovery-only
executionhbrzh passed real existing-replica copy adoption at07:42:42UTC. Source0002
became clone0003; every non-version row and source bytes were preserved, with
integrity/FK checks. No new serving image, live schema or traffic change occurred.
This focused operator check neither invokes a build nor bypasses its lock. A
fresh post-drain snapshot and explicit live adoption remain necessary. Legacy
roster/history preservation, authority/owner mapping, rollback and public-domain
cutover remain open. Further original-scope work includes grading policies/terms,
true API pagination and large exports, dedicated runtime IAM, broader PostgreSQL
workflows and real-provider AI quality evaluation. Keep the original goal active.

## Verified continuation checkpoint: offline import and truthful risk

Source `c2812f4` is pushed to main and passed CI36987004974, all release gates:
1081 API tests/one known passcode-logout xfail, 119 web, 4 browser and 82 E2E
tests, strict types/lint, frontend and Docker builds/auth smoke. Independent
implementation reviews approved the adapter and unknown-risk integration.
Initial CI caught trusted prompt metadata inside the untrusted roster block and
a timer-based calendar-test assertion; specific fixes restored the existing
security boundary and awaited rendered state without weakening assertions.

The exact private legacy archive converted to a new restricted bundle: 11
courses, 33 sections, 30 students, disabled synthetic principal, all ownership
chains/head0003/integrity checked, zero fabricated event/cache/auth/usage rows.
Original bytes and every native row survive backup/restore. Read-only metrics
show30unknown and foreign-owner0. Bundle upload is exclusive, private and
SHA256-roundtrip verified. See LEGACY_IMPORT_PLAN.md for curated hashes/location;
private mappings/content remain outside Git and hosted memory.

The protected c2812f4 serving-image build returned exit75 before Cloud Build
began. Do not retry unchanged or bypass the shared lock. Fresh service metadata
at09:00:48UTC confirmed native00006-cjv/staging00001-7kx/legacy00018-t58 each
Ready at100% of its service. No production or staging routing/config changed.
Shared Graphify refresh passed (164478nodes); native corpus coverage remains
absent, so code conclusions used verified live source. Agent Hub did not
recognize this repository's memory scope; these committed documents are the
verified handoff, with no private transcript upload.

Next bounded implementation is server-revocable passcode sessions, planned in
docs/plans/passcode_session_revocation.md. Retained historical access is planned
in docs/plans/legacy_archive_access.md. Dataset authority/merge, final ownership,
recoverable rollback, final writer drain and domain acceptance remain open,
alongside grading policies/terms, pagination/exports, dedicated runtime identity,
broader PostgreSQL and real-provider AI evaluation. The original full overhaul
goal stays active and has not been reduced to these completed milestones.

## Verified continuation checkpoint: passcode server revocation

Reviewed source `583cfc0` is pushed in `881a2af`;
[CI36989700391](https://github.com/jckail/superteacher/actions/runs/36989700391)
passed every release gate: 1113 API tests, 119 web tests, 4 browser tests, 82 E2E
tests, types/lint, frontend build and Docker auth smoke. The former copied-cookie
logout xfail now passes. Strict v2 signed cookies need a matching live owner-owned
full-cookie-hash row; accounts opaque-cookie guards apply to reads and revocation
writes. Atomic passcode rotation preserves earlier sessions after DB insertion or
commit failure. Conditional monotonic SQL avoids three reproduced independent-
connection refresh/logout/expiry races.

153 focused cases and fresh independent spec/quality review passed. Real database
logout with real chat and a fake provider proves stream/client cleanup and capacity
release on the original portal. Polling/reset do not refresh idle lifetime;
expiry, disabling and logout close sockets with 1008. No migrations, settings or
real provider calls were added. Accounts login keeps its prior transaction policy;
passcode login purges only owner rows past database absolute expiry, preserving
adopted-owner accounts idle policy. V1 cookies need one new sign-in on release.

The protected `881a2af` build stopped with exit75 before Cloud Build; log
`/tmp/st-release-881a2af-build.log`. No new image, deployment or traffic mutation
occurred. Fresh service metadata at 09:31:52 UTC confirmed the native, staging
and legacy serving revisions remain Ready at 100% of their respective services.
Final shared Graphify refresh passed (164478 nodes); native coverage is still
absent, so source conclusions use inspected live code.

The full goal remains active. Pagination/exports are planned in
`docs/plans/roster_pagination_exports.md`: an additive cursor API first, explicit
Unicode/order and derived-scan boundaries, then client and export migrations.
This is planning evidence, not an implemented performance result. Historical
access remains planned separately from auth release. Preservation and ownership of both native and legacy
datasets, final freeze, compatible rollback, writer drain, domain acceptance,
grading terms, dedicated runtime identity, broader PostgreSQL workflows and
real-provider AI evaluation remain open.

## Verified continuation checkpoint: roster paging and streamed exports

Reviewed source `3e6629c` is pushed to main and the feature branch. Roster API
and client use bounded pages with in-memory header continuations, deterministic
Unicode/order and exact counts. CSV/account JSON stream column records with
joined cleanup on disconnect/repeated cancellation. Full metric/history scans,
wide rows/single values, live-read consistency and browser blob buffering remain
explicit limitations. CORS and real PostgreSQL server-cursor/history regressions
are included. Exact-source CI36996126364 passed all gates: 1195 API tests without
skips/xfails, 137 web tests, four browser tests and 83 E2E tests.

Protected Cloud Build3bc0704a succeeded. Its immutable source-bound image is
serving isolated staging00002-jqp on a fresh replica prefix, with AI/demo disabled
and max one instance. Synthetic writes, transfer/history, precision, paging and
exports, readiness and copied-cookie revocation passed; independent replica
recovery execution `superteacher-overhaul-recovery-3e6629c-k4hx7` and staging
readback passed with integrity/FKs/native head `0003` and preserved synthetic
history/raw precision. [Deployment status](DEPLOYMENT_STATUS.md) records exact
identifiers. Production/domain mappings remain unchanged. Shared Graphify refresh
passed with 164478 nodes, zero duplicate IDs/dangling edges; native source coverage
is still absent and conclusions use current inspected source.

Saved-scope hydration/error fallback is a confirmed preexisting UI issue; a
separate shell-preserving fix is in progress. Offline operator archival history
access is being implemented with synthetic fixtures; real ownership/recipient
authorization and native integration remain unresolved. The original overhaul
goal remains active, including terms/grading policies, other complete HTTP
representations, browser downloads, least-privilege runtime identity, broader
PostgreSQL and real-provider AI evaluation, final data authority/merge, writer
drain, compatible rollback and domain cutover.
