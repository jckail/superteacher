# Deployment status and execution handoff

Updated 2026-10-02. Deployment is authorized. Root owns release execution and
verification. The native overhaul is merged and isolated staging is deployed;
production service traffic and custom-domain mappings remain unchanged. Private
backup artifacts stay outside Git and hosted project memory.

## Current checkpoint and next action

Source `07974de1753012da8a91d7d315bf2598925f0e8b` is pushed to main and the
working branch. Exact-source
[CI37007214732](https://github.com/jckail/superteacher/actions/runs/37007214732)
passed all gates: 1294 API tests without skips/xfails (including the new real
PostgreSQL nested-cursor summary case), 194 web tests, four browser tests and
83 E2E tests, lint/types/build, restricted-directory Docker/auth smoke and the
informational benchmark. Independent backend/client reviews passed.

This release adds owner-qualified class-summary column reads with bounded
student/history batches, preserving native metrics and exact statistics. Scalar
aggregates, exact medians, assessment width, long individual histories and the
complete attention response still grow; no total CPU/RSS/latency bound or database
snapshot is claimed. Gradebook captures and displays its server `as_of`, refreshes
on validated forward school-day changes and defers to pending score writes.
Template wording now says “earlier work” without inventing an academic term.
Stored grading policies, terms and dated enrollment are still future work.

Protected Cloud Build `1762afb6-60b9-4f5b-94f1-f06016f2c600` succeeded at
12:42:28 UTC from an immutable Git archive (SHA256
`778afd78ff710c8911b1841ba413ea7a2188e39a22f81698a0b8ba521d6b54bd`).
Image: `gcr.io/portfolio-383615/superteacher@sha256:8f39a734a448ded639687501960bce4a38b20c3d86da8c016ae009909400cd2c`.
Ready staging revision `superteacher-overhaul-staging-00005-klh` serves it at 100%,
with full-SHA VERSION and a verified fresh replica prefix
`overhaul-staging/07974de1753012da8a91d7d315bf2598925f0e8b-08e06248b6cb`.
AI/demo disabled; max one instance, no minimum. Synthetic HTTP checks passed
creation/transfer/history, summary statistics/cutoff, Gradebook cutoff/raw precision,
scoped header continuations/counts, Unicode/BOM/CRLF CSV, historical account JSON,
section preflight, login/logout and copied-cookie revocation. Private credentials
and receipts stay outside Git. Recovery-only execution
`superteacher-overhaul-recovery-07974de-xq7gr` succeeded at 12:56:40 UTC.
The exact image/prefix restored into fresh transient SQLite and verified integrity,
foreign keys, native head `0003`, transfer history, notes, attendance and both
raw extra-credit values. It overrides the entrypoint and never starts a server or
replica writer. Both structured restore proofs and subsequent staging receipt
readback passed. This proves the staged fixtures restored, while final production
drain and zero-loss RPO remain unproven. Fresh metadata confirms native `00006-cjv`
and legacy `00018-t58` remain Ready at 100%; production traffic/domains are unchanged.

Next: independently review the same-minor Python runtime update and Overview
attention retention as separate next slices. Full terms/policies/enrollment,
real-data owner/recipient authority, least-privilege runtime IAM, AI evaluation
and final production cutover remain open. The original overhaul goal is active.

### Previous verified release

Source `4f7ba66bb320c4453dbe39afc9ce8246a4dc208c` is pushed to main and the
working branch. Exact-source
[CI37003990788](https://github.com/jckail/superteacher/actions/runs/37003990788)
passed every gate: 1266 API tests without skips/xfails (including real PostgreSQL),
184 web tests, four browser tests, 83 E2E tests, lint/types/build, Docker/auth smoke
and the informational benchmark. The Docker job reproduces mode-0700 source
directories before building and verifies startup as the nonroot runtime user.
This release includes saved-scope readiness, the bounded Reports student picker
and expected-section preflight, the offline archive viewer and its importer-source
compatibility guard. Independent reviews and focused checks passed.

Protected Cloud Build `258adca0-b0b4-43de-8a32-39e992bcad80` succeeded at
12:05:08 UTC from an immutable Git archive (SHA256
`9a42ccf28829c6ad31c8dfbe215227aaff21ee2d39fd78ffb365a8c61c3e7659`).
Image: `gcr.io/portfolio-383615/superteacher@sha256:0b1cf21c796876f6aa492f5956913b78ebd61d401c044d4eb23648bb0283c301`.
Staging revision `superteacher-overhaul-staging-00004-hlb` previously served it at 100%,
with full-SHA VERSION and a verified fresh replica prefix
`overhaul-staging/4f7ba66bb320c4453dbe39afc9ce8246a4dc208c-c7513fa2af8a`.
AI/demo disabled; max one instance, no minimum. Synthetic creation, transfer,
history/raw precision, login/logout and copied-cookie revocation passed. Extra
HTTP checks passed scoped header continuations/counts, Unicode/BOM/CRLF CSV,
historical account JSON, transferred-student section-preflight rejection and a
matching-section template draft. Private receipts/credentials stay outside Git.
Recovery-only execution `superteacher-overhaul-recovery-4f7ba66-p4rlv` succeeded
at 12:12:26 UTC. The exact image/prefix restored into fresh transient SQLite and
verified integrity/FKs/head `0003`, transfer history, notes, attendance and both
raw extra-credit values. Its entrypoint is overridden: it never starts a server
or replica writer. Structured logs and subsequent staging receipt readback passed.
This proves those staged records restored; final production drain and zero-loss
RPO remain unproven.
Fresh metadata confirms native `00006-cjv` and legacy `00018-t58` remain Ready at
100%, with no production traffic/domain change.

Class-summary and Gradebook cutoff follow-ups subsequently shipped in `07974de`,
as recorded above. Broader model and production acceptance remain open.

### Earlier rejected candidate and preserved successful release

Source `aeb32ad` is pushed to main and the working branch. Exact-source
[CI37000556887](https://github.com/jckail/superteacher/actions/runs/37000556887)
passed all gates: 1252 API tests without skips/xfails, 166 web tests, four browser
tests and 83 E2E tests. It includes the reviewed saved-scope fix (`6f86251`) and
offline archive viewer. The viewer also validated the preserved private rehearsal
bundle's compatibility counts without creating a recipient report or approval.

Its Cloud Build succeeded, but staging revision `00003-zv9` failed before receiving
traffic: private archive extraction created root-owned nested directories with
mode 0700, preventing the nonroot runtime from importing router modules. Existing
revision `00002-jqp` remained at 100%; fresh public health/version probes confirmed
healthy database access and source `3e6629c`. The failed image and replica prefix
are preserved. Docker correction `59d406a`, the CI reproduction and a fresh image
resolved this in release `4f7ba66`. The failed prefix was not reused. Its first
combined CI run found an ambiguous legacy Student locator; `4f7ba66` narrows that
locator without weakening assertions and adds distinct-ID/duplicate-name coverage.

Source `3e6629c` implements roster pagination (`4ad8c5b`), CSV streaming
(`5890342`), account JSON streaming (`464136a`), and the roster client
(`9504fc1`), with independent task and integrated source review approval. Root's
focused verification passed 67 pagination/CSV cases, 12 account-stream cases,
two CORS cases and 50 frontend/session cases. This source includes the
cursor header to the explicit CORS allowlist and two PostgreSQL acceptance cases;
those database cases skipped locally because no test URL is configured.
Exact-source [CI36996126364](https://github.com/jckail/superteacher/actions/runs/36996126364)
passed every gate: 1195 API tests without skips/xfails, 137 web tests, four
browser tests, 83 E2E tests, strict lint/types, frontend build, Docker/auth smoke
and the informational benchmark. The PostgreSQL cases executed. The previous
candidate's two stale test mocks and browser interceptor were corrected without
weakening recovery assertions before this successful run.

Protected foreground Cloud Build `3bc0704a-fe6a-4264-80b8-e1ef47ec0b8b`
succeeded at 10:51:11 UTC from a Git archive of that exact source (SHA256
`b70b141fc4298f98cd53f1be3cbbf427e5dcb3af5fcee1a7c6f818c23353af20`).
Image: `gcr.io/portfolio-383615/superteacher@sha256:64212aa76b885ce196c59eba50388a91f096b390f952d1bd82a27c7029907c81`.
Isolated staging revision `superteacher-overhaul-staging-00002-jqp` served it,
with VERSION equal to full source SHA and a verified fresh replica prefix
`overhaul-staging/3e6629cdacd622721290a9d4ff4c89b4d78cbe9b-b59e6468eb20`.
AI/demo disabled; max one instance, no minimum. Synthetic creation, raw precision,
transfer/history, readiness, login/logout and copied-cookie revocation passed.
Additional HTTP checks passed scoped cursor continuations/counts, Unicode/BOM/CRLF
CSV with raw extra-credit points, and historical account JSON. Private proof and
credentials remain outside Git. Recovery-only execution
`superteacher-overhaul-recovery-3e6629c-k4hx7` succeeded at 11:00:15 UTC:
the exact image restored the new replica into a fresh transient SQLite copy and
verified integrity/FKs/native head `0003`, transfer/history/notes/attendance and
both raw extra-credit scores. It overrides the entrypoint and never starts a
server or replica writer. Subsequent staging receipt readback passed. This proves
those staged records restored; production restart, final drain and zero-loss RPO
remain unproven. Fresh service metadata confirms native `00006-cjv` and legacy
`00018-t58` remain Ready at 100%; production traffic/domains were not changed.

The roster loads 50 rows on demand and preserves filter/sort URLs. Previous/Next
uses transient header cursors; numbered links restart at the first page with a
notice. Ranking/output bounds do not remove full metric/history scans. CSV
assessment width and account single-record values still scale allocations;
browser blob downloads remain buffered. Streams join cleanup before response
exit, including repeated cancellation. Live reads are not database snapshots.
See [roster_pagination_exports.md](plans/roster_pagination_exports.md).

At the earlier `3e6629c` checkpoint, the saved-scope fix was merged and had passed
exact CI but was not part of that image. It now serves in `4f7ba66`, preserving
shell/signout and distinguishing pending, failed, missing and valid empty scopes.
The offline archive viewer also serves in the newer image;
real-data recipient/owner approval and native authenticated integration remain open.

Linear/Obsidian integrations are unavailable in this session, and Agent Hub does
not recognize this repository scope; Git documents and local task ledgers retain
the verified handoff without inventing an external issue or uploading private data.

Source `583cfc0` implements server-revocable passcode sessions using the existing
session table, with independent spec/quality review approval and 153 focused
auth/accounts/WebSocket cases passing. Signed v2 cookies require a live owner
session; logout revokes copied cookies, login rotation is atomic, accounts wire
formats guard reads and writes, and conditional SQL prevents stale refresh races.
A real database/fake-provider test proves active-chat cancellation and capacity
release. Legacy v1 cookies require one new sign-in after deployment. No migration,
real provider call, production configuration or serving image change occurred.
Exact-head [CI36989700391](https://github.com/jckail/superteacher/actions/runs/36989700391)
passed every required gate and the informational benchmark at `881a2af`: 1113
API tests with no remaining logout xfail, 119 web tests, 4 browser tests, 82 E2E
tests, strict types/lint, frontend build and Docker build/auth smoke. The protected
new-source image build stopped with shared-lock exit75 before Cloud Build began;
log `/tmp/st-release-881a2af-build.log`. Do not retry unchanged or bypass the lock.
The Git archive context hash is
`600f37451344560c3419e1674c50f6ced98f1fb0c350b3d14eae9a839f0483b2`.
At 09:31:52 UTC, fresh metadata confirmed native `superteacher-00006-cjv`,
staging `00001-7kx`, and legacy `edutrack-00018-t58` still Ready at 100% of
each service. No new serving image or deployment occurred. See
[passcode_session_revocation.md](plans/passcode_session_revocation.md).

Offline legacy roster conversion is implemented at `8291cae`, with 54 focused
synthetic tests and independent review approval. The exact private API archive
rehearsal and full-row backup/restore passed: 11 courses, 33 sections, 30 students,
zero fabricated events, native head `0003`, ownership/integrity checks, original
bytes preserved. The target is an explicitly disabled synthetic principal.
Source `9a8da6a` adds truthful unknown risk across metrics, REST, reports, AI tools
and UI; read-only checks of the converted database show all 30 unknown and zero
foreign-owner rows. See [LEGACY_IMPORT_PLAN.md](LEGACY_IMPORT_PLAN.md) for hashes
and limitations. Source `79ee831` preserves the displayed report section when
opening unknown roster records; 11 focused UI tests and independent re-review
passed. Initial integrated [CI36986440202](https://github.com/jckail/superteacher/actions/runs/36986440202)
passed lint and both browser suites (4 and 82 cases), but found prompt-boundary
shape failures and an asynchronous calendar-test assertion. Source `91b3662`
corrects both: 165 focused security/risk/context tests and four calendar tests
passed without weakening assertions. Corrected exact-head
[CI36987004974](https://github.com/jckail/superteacher/actions/runs/36987004974)
passed every required gate and the informational benchmark at `c2812f4`: 1081
API tests plus one known passcode-logout xfail, 119 web tests, 4 browser tests,
82 E2E tests, strict types/lint, frontend build, Docker build/auth smoke. A new
serving image remains pending.

The protected build of immutable source `c2812f4` stopped with exit75 before
Cloud Build began when another session acquired the shared lock. Log:
`/tmp/st-release-c2812f4-build.log`; do not retry the unchanged attempt or bypass
the lock. The source context was exported from Git (archive SHA256
`b8c922ed10cdcf6fe5d371e63efd66ebd0371038460ac173613a3d5aa5ab5451`),
excluding untracked local material. At 09:00:48 UTC, fresh service metadata
showed native `superteacher-00006-cjv`, staging `00001-7kx`, and legacy
`edutrack-00018-t58` each still Ready at 100% of its respective service.
No deployment or traffic mutation occurred.

The implemented authentication change still needs a new serving image and
deployment. Other
original-scope work remains: [historical archival access](plans/legacy_archive_access.md),
grading policies/terms,
[API pagination/large exports](plans/roster_pagination_exports.md), dedicated
least-privilege runtime identity, broader
PostgreSQL workflows and real-provider AI evaluation. The full overhaul is active.

Main source `5113de8` passed every gate in
[CI36978867068](https://github.com/jckail/superteacher/actions/runs/36978867068),
including **996 API tests and one known legacy-passcode logout xfail**. It adds
staging/drain and candidate replica-binding safeguards, with 25 focused mocked
deployment cases. Earlier source `9de97ce` passed all gates with 976 API tests and
adds exact pinned Litestream bookkeeping validation to the offline accounts
adoption helper. Neither change alters teacher-facing routes or frontend behavior.

The protected image build for this source stopped with exit75 at the shared
verification lock before any Cloud Build command/archive/image began. Log:
`/tmp/st-cloud-build-9de97ce.log`. Do not repeatedly queue the unchanged attempt
or bypass the lock. The deployed staging image below remains source `7166813`.
The corrected helper's private production-copy rehearsal now passed as described
below. A new serving image has not been built. A final post-drain snapshot,
compatible rollback and explicit live adoption/promotion procedure remain required.

The legacy API archive is preserved locally and in private versioned GCS with
verified SHA256 roundtrip; see [LEGACY_CUTOVER.md](LEGACY_CUTOVER.md). It is a
non-atomic API archive, not a consistent database backup. Preserve the existing
legacy data during the overhaul. Offline roster import is verified; production
dataset authority/merge and ownership, compatible rollback, final writer drain
and domain cutover remain open.

## Verified native staging release

PR15 merged as `8ceb050` from tested source `7166813`. Exact source CI
[36970806343](https://github.com/jckail/superteacher/actions/runs/36970806343)
and merged-main CI
[36971521702](https://github.com/jckail/superteacher/actions/runs/36971521702)
passed every release gate. Source API evidence: **963 passed, one known xfail**.

Cloud Build `8e3a2ff4-19a1-421d-a0e8-c0de66687f29` succeeded. Image:
`gcr.io/portfolio-383615/superteacher@sha256:5d3c85dfb754bf5382ca7f196d86b108d878c2a85ccf2425702d22b0df7bcde6`.
Its exposed VERSION is the build ID, mapped to source `7166813`; it is not a Git SHA.

Isolated service `superteacher-overhaul-staging`, revision
`superteacher-overhaul-staging-00001-7kx`, is deployed at
https://superteacher-overhaul-staging-vbufkr2qma-uc.a.run.app.
It uses a separate replica prefix
`overhaul-staging/8e3a2ff4-19a1-421d-a0e8-c0de66687f29`, demo/AI disabled,
UTC calendar, passcode auth, max one instance and no minimum instances.
Health, readiness, actual login/calendar/version/SPA/logout passed. The reusable
candidate check passed synthetic course/initial-section/student/assessment/note/
attendance creation, exact raw 20.123456789/10, name edit, transfer/history,
active-section averages, rosters and authenticated logout. Private credentials and
receipts remain outside Git, mode0600; values are not included here.

Recovery-only job `superteacher-overhaul-recovery-8e3a2ff4`, execution
`superteacher-overhaul-recovery-8e3a2ff4-9jlsw`, restores the isolated prefix into a
fresh transient SQLite copy and checks the receipt. It overrides the entrypoint,
never starts the server or replication, and cannot write the serving database.
Execution succeeded at06:03:56 UTC. Its structured result confirms native0003,
integrity/FK success and preserved synthetic transfer history/records. The
candidate receipt readback also passed. This proves the staged replica can restore
the checked records; it does not prove a production restart or a zero-loss RPO.

A separate rehearsal job `superteacher-overhaul-adoption-8e3a2ff4`, execution
`superteacher-overhaul-adoption-8e3a2ff4-5wggt`, restores the existing service's
replica into a private transient copy and runs the adoption bridge there. It never
starts replication/server or writes the production prefix. The first execution correctly rejected restore-created SQLite sidecars. After
preparing a validated standalone backup, execution `vtgs9` reached exact-schema
validation and refused the copy because its schema differs from the frozen
published accounts0002 baseline. No output copy was published and no live schema
changed. The schema-only diagnostic execution `mnl7l` succeeded: all application/accounts
schema matched; only `_litestream_lock` and `_litestream_seq` were additional.
The bridge now reconstructs and validates the exact two-table DDL from pinned
Litestream0.5.17 in both independent expected schemas and preserves every internal
row. Missing pairs, extra columns/indexes/triggers and DDL drift remain rejected.
Twenty focused adoption tests passed, including real pinned local replication,
standalone backup and adoption. Exact-head CI subsequently passed (976 API
tests). A later bounded artifact rehearsal closes the production-copy
compatibility check without claiming a new serving image. A final cutover still
requires fresh post-drain adoption and verified serving-image configuration.

### Corrected helper against the real replica copy

Execution `superteacher-overhaul-adoption-8e3a2ff4-hbrzh` succeeded at
07:42:42 UTC. It overrides the existing immutable source7166813 recovery runtime's
entrypoint with a checked operator payload. The payload verifies the committed
source9de97ce helper SHA256
`f9247a09b83c7b6b611eae30635c9bfb1551478aee447937773d03f00cbf403e`
and six supporting source/migration hashes before any restore. Relative imports
use the actual image package; no dependency install or image build occurs.

The task restores the existing service replica into a private transient directory,
prepares a standalone read-only backup and adopts only a clone. Independent checks
confirm source0002/output0003, every non-version row preserved, unchanged source
snapshot bytes, integrity and foreign keys. The structured Cloud Logging result
was independently read and verified; a local mode0600 proof is retained at
`/tmp/st-9de-production-copy-proof.json`. Limits: one task, no retries, 180 seconds,
512Mi memory, 100-second restore deadline and 32Mi restored-file cap.

No server, replication writer, production schema change or promotion ran. The
source replica was read only; the existing runtime identity still has broader
IAM rights, so this is a code-mediated restriction, not an IAM-enforced read-only
principal. Transient clones were removed after verification. The existing service
can continue writing after this restore; final cutover needs its own fresh
post-drain snapshot. This targeted operator-artifact check does not validate a
new serving image or replace the shared build lock.

Public recheck after staging: www.the-super-teacher.com reports `v0.1.0`;
the existing direct superteacher service reports `dae26a5`, revision00006-cjv at
100% traffic. No production/domain/serving-prefix changes were made. Existing
accounts-0002 adoption, tested restored copy, single-writer drain and data-preserving
custom-domain cutover remain required. Request-based CPU may stall background
replication between requests; the pilot's documented RPO caveat remains.

## Latest release continuation

Later read-only metadata reported `superteacher-00006-cjv` at 100% traffic,
image `superteacher:dae26a5`. The observation table below is historical; its
`ce94d50` digest must not be used as evidence for the current release. Custom
domain mappings were still to legacy `edutrack` at the last verified inspection.
Reinspect all service/domain metadata before an authorized traffic change.

The native accounts merge preserves integrity `0002` and adds accounts `0003`.
The serving image may already have independently published accounts `0002`;
startup refuses that ambiguous history. Validate a consistent backup/clone with
an explicit schema adoption bridge before promoting against the existing prefix.
An isolated empty-prefix candidate can validate the new chain independently.

An earlier protected build attempt also stopped at the shared heavy lock; the
later source7166813 image and isolated deployment succeeded as recorded above.
The latest source9de97ce image attempt is blocked at that lock. Avoid overlapping
the independent persist deployment session or changing its processes.

## Historical targets (04:50 UTC)


Explicit project: `portfolio-383615`; region: `us-central1`. The gcloud active
credential is authenticated; its configuration has no default project. No local
ADC file was present; Terraform/library credentials need a separate probe before
using them. CLI authentication alone does not establish ADC or provisioner IAM.

| Target | Ready revision / traffic | Image / public result |
| --- | --- | --- |
| `superteacher` | `superteacher-00004-dgh`, 100% | `superteacher:ce94d50`; health 200, version `ce94d50` |
| `edutrack` | `edutrack-00018-t58`, 100% | `edutrack:v0.1.0`; `/api/health` 404, version `v0.1.0` |
| Both `the-super-teacher.com` and `www.the-super-teacher.com` | Ready domain mappings to `edutrack` | Version `v0.1.0` |

Direct current candidate target:
`https://superteacher-vbufkr2qma-uc.a.run.app`. Current immutable digest:
`gcr.io/portfolio-383615/superteacher@sha256:e9757073f09b46f0b3b9f01d056e12c8cdc63978d660d44bebbab079c4a39b72`.
The ready revision was created at 04:47 UTC. This supersedes the older
`c344911` observations in `RELEASE_PLAN.md`.

Both services use `292025398859-compute@developer.gserviceaccount.com`.
That identity has project `roles/editor` and
`roles/secretmanager.secretAccessor`, plus bucket-scoped object admin below;
it is not a least-privilege dedicated runtime identity. Changing it requires
preserving current secret and replica access.

Superteacher has 1 vCPU, 512 MiB, concurrency 80, request timeout 300 seconds,
revision maximum one instance, no configured volume or Cloud SQL attachment.
Environment names inspected: `SEED_DEMO_DATA`, `VERSION`,
`LITESTREAM_REPLICA_URL`, `AUTH_PASSWORD`, `SESSION_SECRET`,
`ANTHROPIC_API_KEY`. The latter three reference their existing Secret Manager
names; each currently has enabled version `1`. Other environment values were
not printed. Cloud SQL project inventory is empty and
`superteacher-database-url` is absent.

## Historical initial persistence inventory (04:50 UTC)

Fresh `origin/main` is `ce94d5062a77fce2acfa8e698ecc0082ecc311cb`.
Its accepted `docs/adr/0001-persistence.md` selects the Litestream pilot.
Retaining this path needs no new Cloud SQL instance.

The live non-secret replica URI is
`gs://portfolio-383615-superteacher-litestream/superteacher`.
Bucket metadata: Standard, US-CENTRAL1, uniform bucket-level access, enforced
public-access prevention, object versioning enabled, 7-day soft delete, and
14-day deletion of noncurrent objects. Its explicit policy has no `allUsers`
or `allAuthenticatedUsers`; the runtime identity has `roles/storage.objectAdmin`.
Legacy project owner/editor/viewer grants remain. Metadata inventory found
12 LTX objects totaling 34,483 bytes, updated between 04:47 and 04:49 UTC.
These prove replica objects exist, not restore correctness or a guaranteed RPO.
No object payload was downloaded.

Origin's entrypoint restores before starting the app and exits on restore
errors. It also allows first boot when no replica exists, so a typo in a
production prefix can create an empty dataset: verify the exact URI before
deployment. Keep the native Cloud Run SQLite guard compatible only with the
explicit validated replication branch. Keep demo seeding disabled.

## Safe staged execution

1. Root integrates current main, reconciles entrypoint/configuration and runs
   checks on the actual immutable release. Native integrity migration `0002`
   must remain intact; identity integration has its separate migration issue
   documented in `IDENTITY_INTEGRATION.md`.
2. Build the image without running either existing `cloudbuild.yaml` deploy
   step. The resolved YAML is now build-only; incoming origin YAML deployed straight
   to serving traffic. Build-only command after source checks:

   ```bash
   task_release_sha=$(git rev-parse HEAD)
   /home/jkail/.local/bin/agent-heavy-check -- gcloud builds submit --project=portfolio-383615 \
     --tag="gcr.io/portfolio-383615/superteacher:${task_release_sha}" .
   ```

3. Deploy and verify a separate `superteacher-staging` service with an isolated
   replica prefix and synthetic data. The staging service must never use the
   live prefix. Keep current secret references, runtime account, single-writer
   limits, timezone and proxy settings explicit:

   ```bash
   gcloud run deploy superteacher-staging --project=portfolio-383615 \
     --region=us-central1 --image="gcr.io/portfolio-383615/superteacher:${task_release_sha}" \
     --service-account=292025398859-compute@developer.gserviceaccount.com \
     --allow-unauthenticated --max-instances=1 --min-instances=0 --memory=512Mi --cpu-boost \
     --set-secrets='AUTH_PASSWORD=superteacher-auth-password:1,SESSION_SECRET=superteacher-session-secret:1,ANTHROPIC_API_KEY=anthropic-api-key:1' \
     --set-env-vars="SEED_DEMO_DATA=false,VERSION=${task_release_sha},FORWARDED_ALLOW_IPS=*,SCHOOL_TIMEZONE=UTC,LITESTREAM_REPLICA_URL=gs://portfolio-383615-superteacher-litestream/staging-${task_release_sha}"
   ```

   Use the returned staging URL for health/version, protected 401, authenticated
   workflows, fault rollback and persistence across replacement. Reconcile UTC
   with the selected school timezone before promoting.
4. Before live migration, capture a private consistent restore/export and
   validate a copy with native `superteacher.backup`. Record source URI,
   timestamp, schema version, row counts and integrity outcomes without student
   contents. Rehearse the new migration on that copy. Preserve the original
   replica and restore point throughout the recovery window.
5. `scripts/deploy_cloud_run.sh` requires an explicit service and replica prefix.
   Undrained staging is restricted to the named isolated candidate service,
   isolated prefix and operator isolation acknowledgment. Every shared-prefix
   stage and every promotion requires observed writer-drain evidence. The
   helper checks the recorded serving revision before building and again before
   deploying a shared-prefix candidate. Deployment flags do not suppress
   Litestream restore/replication when a candidate is later invoked. Confirm
   that no other revision writes the selected prefix, including old staging
   revisions. Promotion privately verifies the candidate has exactly one literal
   replica URL matching the supplied bucket/prefix before changing traffic.
   Use the independently verified isolated service for checks. Isolation and
   final drain remain observed operator evidence, not facts this helper proves.
6. Establish a maintenance/quiesce interval that stops new writes and closes
   existing chat sessions; verify the old writer has drained and final replica
   sync completed before starting the new writer. Traffic movement alone does
   not prove this: revision maximum-one does not prevent rollout overlap.
   The script checks the recorded serving revision against the operator
   precondition; it cannot observe writer termination or final sync itself.
   Production promotion still requires that concrete drain step to be observed. Then direct
   100% to the named candidate revision and run authenticated persistence
   verification. Record revisions explicitly instead of `--to-latest`.
7. Rollback must account for schema compatibility. The observed existing replica
   uses independently published accounts `0002`; native head is combined `0003`.
   Recheck the exact old image's supported chain rather than relying on historical
   `ce94d50` evidence. Prepare a compatible rollback image, or restore
   into a separate recovery prefix with a recorded policy for writes since
   cutover. Do not overwrite the live replica to roll back an image.
8. Keep custom domains on `edutrack` until the above is verified. Afterward,
   execute the selected domain cutover while retaining the previous routing
   metadata. Domains and direct service presently serve different products.

[Cloud Run deployment health-check documentation](https://docs.cloud.google.com/run/docs/deploy-functions#disabling_the_deployment_health_check)
describes the default startup invocation; the installed CLI exposes
`--no-deploy-health-check`.
[Cloud Run autoscaling documentation](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
explains revision overlap during deployment.

## Legacy export and remaining evidence

The initial read-only inspection found that legacy public OpenAPI metadata lists `/api/db/classes`, class sections/students,
`/api/db/students/{student_id}` and student grades. It exposes no backup/export
route. A reviewed export must traverse those read endpoints into private
storage, preserve IDs/schema/grades, and check consistency while writes are
quiesced; alternatively capture its actual underlying storage using its own
supported administrative path. A later authorized API archive is now retained
privately, with limits and durable-copy evidence in `LEGACY_CUTOVER.md`. Historical
ADR log observations suggest sample-data initialization, but they do not prove
the current service has no records worth preserving. Do not delete/restart it
based solely on that assertion. Its old image availability must also be checked
before promising an old-image rollback.

Litestream restore of the live prefix into a restricted **new local file** is
the current Superteacher export path. Run the pinned Litestream tool with a
read-authorized identity; never restore over the live file, launch a writer on
the source replica, print records, or upload them into task notes. Save the
snapshot outside the repository. The schema-only production-copy diagnostic
succeeded and the corrected helper passed the private-copy artifact rehearsal
above. Final post-drain adoption and production recovery still need their own
execution evidence. Isolated staging restoration is already verified above.

## Cost and optional PostgreSQL preview

The existing pilot avoids a new always-on database bill. Illustrative GCS cost
before free allowances: 1 GiB Standard in us-central1 plus 100,000 Class A and
100,000 Class B operations is approximately $0.56/month ($0.02 + $0.50 + $0.04),
excluding additional versions, soft-deleted data, network and Cloud Run/AI.
Usage is not inferred from the small metadata inventory.
[Google Storage pricing](https://cloud.google.com/storage/pricing) supplies rates.

If PostgreSQL is later selected, current list-rate arithmetic for the proposed
1-vCPU/3.75-GiB dedicated Enterprise tier at 730 hours is $49.31 compute, plus
about $3.40 for 20 GiB SSD: approximately $52.71/month before backups/network
and other charges. At 100 GiB SSD the corresponding subtotal is $66.31.
This is an optional new recurring cost, not needed for the retained pilot.
[Google Cloud SQL pricing](https://cloud.google.com/sql/pricing) supplies
$0.0413/vCPU-hour, $0.007/GiB-hour and SSD rates; recalculate the exact selected
edition/region in the calculator before execution.

`infra/cloud-sql` remains an optional preview. No Terraform executable was found
on PATH in this pass. Its dry-plan prerequisites are supported Terraform,
verified ADC/impersonation, explicit runtime identity, and reconciliation with
the existing `portfolio-383615-terraform-state` bucket/stack owner. No state
objects were read. Use the isolated preview flow in `CLOUD_SQL_PLAN.md`, including
the deliberately invalid preview credential, without apply/destroy/plan output.
Do not provision it merely to deploy the accepted Litestream branch.
