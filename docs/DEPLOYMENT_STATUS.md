# Deployment status and execution handoff

Updated 2026-10-02. Deployment is authorized. Root owns release execution and
verification. The native overhaul is merged and isolated staging is deployed;
this release operator has not changed production traffic or custom-domain mappings. Private
backup artifacts stay outside Git and hosted project memory.

## Attendance report freshness follow-up (2026-10-02)

Published source `257a657e2ce4c069e4c41eeb7aa60f752ebcdea6` refreshes exactly
the submitted section's deterministic report summary after attendance settles.
It preserves captured section/client ownership across class switches and session
replacement, existing rollback and queued optimism, and Insight/parent-generation
policy. Root demonstrated RED: one control passed and seven settlement cases
failed in 7.698s. GREEN passed 60 relevant tests across four files in 7.54s,
plus TypeScript, focused ESLint and diff checks. Independent task and complete-change
reviews approved SPEC/QUALITY without blocking findings. See
[the bounded plan](plans/attendance_summary_freshness.md).

Exact combined [CI37049099552](https://github.com/jckail/superteacher/actions/runs/37049099552)
passed all seven jobs: 1403 API tests in 191.53s, 350 web tests across 28 files,
four browser tests in 13.6s, 84 E2E tests in 2.0 minutes, and 259 locked Docker
cases in 32.25s, plus lint/types/build/benchmark checks. Root captured private
full logs and CI-state SHA256
`123c9c11fda501a6b4242b7d2e0f1c324f0a13216fd6055c57538be7306265c9`.
The exact archive SHA256 is
`4cd7224dbf7c038e7ebf28c8a88807b85e162f30f0d3ea7d7f7161eb4a94fc80`.
Independent review verified 296 Git-matching files/325 context entries and modes;
root helper validation passed. Protected build session89535 exited0 with
Cloud Build `b524f123-9699-4189-89af-2aeff7a39106` SUCCESS and immutable image
`gcr.io/portfolio-383615/superteacher@sha256:4554d1b067e80152b46053aa088ecdb809e5bb78853fd9b41a22987f1f5c4be6`.
Root verified build state, image digest and proof bindings; private build-proof
SHA256 is `50a73dc4cc557a9990586bb96b6e740fa228939806e69a476f1f5b1621c21a79`.
The private create-only manifest passed independent review. Its local input guard passed after the
owned preflight parent was tightened from0755 to0700; the backup root was already
0700. No candidate phase directory or resource was reserved by that local check.
Root then executed the protected create-only phase (session97376). The sole
create request returned operation `8f52d7c9-0621-4e74-98a8-a9099c12283c`, and the
new service `st-candidate-257a657e2ce4-8b942daad1eb` reports Ready revision
`st-candidate-257a657e2ce4-8b942daad1eb-00001-dzp`. The helper exited1 at
service/revision verification: it required a full resource path in the revision's
parent-service field, while the actual response contains the exact service-name
leaf. Three bounded read-only GETs and local verification isolated only that
guard mismatch; all other configuration guards passed. The original failure and
cleanup receipts remain preserved (temporary request removed, credentials private,
phase not completed). No deployment acceptance proof exists yet. A separately
reviewed read-only continuation is being prepared; do not repeat creation,
alter IAM, update existing staging or infer platform/application handshake success.
The [Cloud Run revision reference](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services.revisions)
describes this field as the parent service's name; live response bindings supply
the observed format. Complete synthetic workflows and isolated restore remain
separate acceptance gates.
Previous d256 and112 admission75 receipts remain preserved; no unchanged retry
is authorized by a source review. The separate Insight freshness gap remains:
its GET can charge quota and generate AI content, so an explicit refresh/provenance
design is still needed before changing its cache policy.

Canonical index refresh completed under its internal shared gate (session34933):
202 files/1761 chunks, no warnings. Four changed evaluator/attendance source and
test files match their indexed live hashes. Shared Graphify refresh was skipped
because another writer was active; native runtime coverage remains absent.
PR71 (`7c9c919`) has independent source review and exact-head CI approval for a
future batch. Keep trusted proxy hops at zero until actual ingress/header suffix
and direct-access exclusion are verified. It is not integrated into this frozen
candidate. Author-owned PR72–75 and dependency updates remain separate work.

## Reports, evaluation and keyboard focus integration (2026-10-02)

Latest follow-up: PR69 head `2582d8c` is now merged as
`d25694ef927dccd228bf0de4032555f117d92610` and published on main and the
working branch. Independent review against the current parent found no conflicts
or blockers. The delta normalizes typographic apostrophes and records the offline
scorer hash; it does not change application AI requests. Root passed 21 standalone
offline tests and focused Ruff checks. The first pytest launch failed before
collection because repository warning configuration requires unavailable local
SQLAlchemy; the standalone run used isolated pytest configuration and no conftest.
Combined [CI37047594086](https://github.com/jckail/superteacher/actions/runs/37047594086)
passed all seven jobs: 1403 API tests in 191.00s, four browser tests in 14.0s,
84 E2E tests in 2.0 minutes and 259 locked Docker cases in 34.78s, plus web,
lint/types/build and benchmark checks. Root captured private full logs and the
CI-state SHA256 `d931db14dcf787651b977d27c74546e9ab50ad7d9d19e81832fb7a34c8814b85`.
The exact archive SHA256 is `6a26a610fc7febc55fa3666b6db5f99ad24dc9ff202108ca5d97da9095a0191a`;
independent review verified all 294 files/323 context entries and modes against
Git. Root helper validation passed before execution. Protected build session81016
exited75 when shared-gate admission expired, before the helper started. No intent,
build proof, image or cloud mutation exists; the private blocker receipt is saved.
Do not retry this source unchanged. No deployment has
executed for this source. Earlier112 build queue75 remains preserved, with no
unchanged retry. The saved goal reports blocked; the user's resume instruction
authorizes continuing the original scope without creating a replacement goal.

Reviewed Reports draft settlement is integrated locally as `890658e` (isolated
`47f5b4f`). Root established RED: unchanged control passed, pending teacher edits
were overwritten. The fix retains current raw subject/message/source and presents
one generated alternative for explicit review, replacement or discard. Copy/email
use the current draft; explicit actions return keyboard focus to Subject. Late
request completion leaves focus alone and cannot reach a new student/tone/section
or authenticated lifecycle. Independent task and complete-branch reviews approve
SPEC/QUALITY. Root final focused checks passed 71 tests across five files in
8.26s, types/lint/diff; combined integration passed 40 tests across three files
in 8.31s and TypeScript. Published source `11249217e32bd299179d930a2e252ecf0f0e9cb4` passed exact
[CI37043235047](https://github.com/jckail/superteacher/actions/runs/37043235047):
all seven jobs succeeded, including 1399 API tests in 186.91s, 342 web tests
across 27 files, four browser tests in 14.2s, 84 E2E tests in 1.5 minutes and
259 locked Docker cases in 33.89s; lint/types/build/benchmark passed. Root
captured actual metadata/full private logs; CI-state SHA256 is
`ad2c5e0216857cac3046a1bba9d08d17e7b16ba6718ec37023eec08ab11f57a0`.
Independent immutable archive/context/helper review and root validate passed.
Archive SHA256 `2d2e3b3d97ba7844a8f724f93bd9f4ff7fe205d3f6418a9b833d0c8321b73690`
contains 323 entries/294 files with reviewed modes. Protected build session56016
exited75 before the helper began: no intent, image or cloud mutation exists.
Preserve its private blocker and do not retry unchanged. Runtime acceptance remains
pending; source CI does not establish a deployed image.

Reviewed PR69 offline evaluator (`90a849f`) and PR70 export focus (`241939f`) are
also integrated locally. Each head passed independent review and all seven CI
jobs. The evaluator's bounded lexical replay and private hashed reports require
human semantic review; no real-model acceptance is claimed. Root ran the checked-in
synthetic example successfully without database/provider calls. Account export
restores focus synchronously before closing its popover, with no late completion
focus theft; root's two component tests passed. Broader real assistive-technology
and provider/privacy/factuality acceptance remain open.

Earlier published notes/demo/admin candidate `1f783001b81899e42ccdc388eb0a65f1bb20e2c7`
passed exact [CI37040671313](https://github.com/jckail/superteacher/actions/runs/37040671313):
1382 API tests in 194.32s, 309 web tests across 25 files, four browser tests in
14.4s, 84 E2E tests in 2.1 minutes, and 259 locked Docker cases in 36.73s;
lint/types/build/benchmark passed. Its immutable archive/context/build helper
was independently approved and actual CI proof captured; no Cloud Build or
runtime deployment was executed for that intermediate source. Build the settled
latest combined candidate after its own exact CI instead.

The latest root staging snapshot records fe2 `00009-bcw`, preserved with its
qualified receipts/original feature failure. A separate create-only private
candidate is being prepared. Root read-only preflight established operator
create/read/invoke permissions, exact runtime actAs, no project public invocation
binding, no parent reported by project GET, and a usable user developer ID-token
route. Exact-SA ID-token mint permission was not returned; no IAM grant was added.
The developer token is not established as service-audience-restricted. Actual
new-service no-token denial/token handshake, configuration, synthetic workflows
and restore still require execution. No candidate service was created by these
probes. Preserve all prior queue75 and failure receipts without unchanged retries.

The private create-only helper is prepared outside Git and independently approved
at SHA256 `4d893b7f9a955f90f03c60e041efbb691cf29b30006b6870e5657508603d72d6`.
Review corrected receipt-schema compatibility, pre-create token acquisition and
revision-read authority checks. Root's controlled missing-manifest entrypoint
check passed with zero CLI/HTTP calls and no phase files. Initial test-harness
bytecode bookkeeping was diagnosed and corrected without cache deletion.
This is preparation/negative-gate evidence only: no manifest, successful112 build,
new service, synthetic workflow, or restore receipt exists. Do not execute until
an eligible accepted artifact and reviewed manifest are available.

Shared Graphify refreshed successfully (164506 nodes) but excludes native
Superteacher source. Canonical code-context indexing completed under its internal shared gate
(session55212): 201 files, 1744 chunks, no warnings. Semantic ParentComposer/Insight
and keyword evaluator/Attendance lookups returned correct current paths; five
changed source files match their indexed SHA256s. Sibling indexes remain absent;
earlier notes index75 was not retried. Semantic CLI and live text discovery work;
Codemogger/LSP MCP are absent from this session and Toolport profile. Agent Hub
has no configured project scope. AgentMon gateway discovery returned no tools;
its dashboard responded200 but registration/heartbeat/feed were not performed. Curated local/Git checkpoints preserve these gaps.
PR69 later advanced to reviewed `2582d8c` (typographic-apostrophe normalization
and scorer hashes); its exact CI passed, but frozen112 contains original90 only.
That nonurgent delta remains a separate integration batch; PR70 is merged.
Remaining priorities: Attendance scoped Insight/summary invalidation; independent
artifact input-day/timestamps/prompt versions; full grading policies; native
production adoption/drain/rollback/domain cutover; dedicated IAM and real
provider/email acceptance; bounded account CLI list output.

## Current checkpoint and next action

Earlier shared-session metadata recorded native production serving `superteacher-00008-96g` at 100%, while legacy remains `edutrack-00018-t58`
and staging remains `superteacher-overhaul-staging-00007-9lq`. The native service
changed in another session; this release operator did not promote it. The B5
acceptance evidence below records the earlier production observations. Read
[RELEASE_CHECKPOINT.md](RELEASE_CHECKPOINT.md) for the other session's migration
lineage and email-delivery blockers; they do not establish acceptance of this
overhaul against the live database.

Earlier published candidate `f423afcad2bfda91b9162f06457e2befee3cde7b` is pushed
to root main and the working branch. PR65 and PR66 were merged at 16:35:09 UTC.
Its exact combined [CI37034932285](https://github.com/jckail/superteacher/actions/runs/37034932285)
passed all seven jobs: 1357 API tests in 160.81s, 287 web tests across 23 files in
31.44s, four browser tests in 14.7s, 84 E2E tests in 2.1 minutes, and 259 locked
Docker compatibility cases in 35.25s; lint/types/build and informational benchmark
passed. Root captured actual metadata and full private logs. This combined run
covers the reviewed Student integration and chat-link/runbook changes; the focused
Docker set remains distinct from the full native API suite inside that image.

Immutable f423 archive SHA256
`d463c058173a68d4b81d7508eeeae0ba6e2608774f86f86dd8aecf522f65ca02`
contains 308 entries/279 files. Independent build-helper source/specification/
quality reviews passed; root validated archive/source byte agreement and the
approved 9011 substitutions in deploy/recovery/smoke helpers. Protected session
20955 completed successfully. Cloud Build `91213e75-fd3b-480a-957e-286180b77003`
accepted the exact archive and produced image digest
`8a01599ed2cb0b49f85d78bf8f9ed32289bca265236f082e69b13628a318ac25`.
Its private proof binds the actual seven-job CI state hash. Protected staging
deployment session 48075 exited 75 before its helper began; no deployment intent,
cloud mutation or f423 deployment/recovery acceptance exists. Preserve the queue
blocker and do not retry unchanged or bypass the wrapper. A fresh read-only
Cloud Run snapshot now records staging `00009-bcw` Ready at 100%, VERSION
`fe2cd01582d288346bb8f9fa565b7938ad7d24ff`, changed by another session.
The prepared B5/failed-23 state guards are stale; reconcile that ownership/state
and review new guards before any future deployment. B5 `00007-9lq` remains the
most recent root-accepted historical runtime, not the currently serving revision. This checkpoint
edit changes documentation only; source CI/artifact remain pinned to f423.

Historical 9011 checkpoint: exact source
`9011f65509e5871c8425a99ebaaa4f17b638ab34` passed all seven jobs in
[CI37028496201](https://github.com/jckail/superteacher/actions/runs/37028496201)
(1357 API in 131.56s, 225 web, four browser, 84 E2E; locked Docker 259 in 35.76s).
Reviewed Docker chmod PR63/documentation PR64 were merged and published. Archive
SHA256 `1ed2b2f022aeaf39e4f22b5aecb0f787b86fe145d8f5b154b20c29e4e4c35d26`
had 305 entries/276 files and reviewed 0644/0755 regular modes, directories 0755
and private roots 0700. Protected session 19785 exited 75 before helper execution:
no intent/proof or cloud call occurred. Preserve this blocker separately; do not
retry its unchanged action or bypass the wrapper. Fresh f423 execution follows a
distinct source/context, fresh preflight and actual lock acquisition.

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

Root's shared Graphify refresh session13424 completed successfully (exit0),
publishing164478 nodes; native Superteacher runtime coverage is still absent,
so this does not replace live-source inspection.

Student follow-up was integrated into the parent in commits:
`037e92f` (original isolated commit `73178da`) adds recorded-detail cutoff/
forward-day refresh, ordinary-error draft retention, fatal typed404 handling and
actual write-ordering regressions (35 new tests). `7e9b627` (original `79f85f3`)
adds captured delete-target/client/lifecycle handling (11 new cases). Both tasks
and the full branch diff have independent specification and quality approval with
no actionable findings. Original worktree:
`/home/jkail/projects/superteacher-student-freshness-20261002`.
Root-executed final focused evidence is 80 tests across eight files in 7.04s, with
types, focused lint and diff checks passing. Publication and full combined exact CI are complete at f423; staging/recovery acceptance remains pending; the immutable build is accepted. Independent Insight, generated-draft provenance and
new-after-submit note settlement remain separate. Opening note B during a pending
note-A modal has not been established as reachable; note/accessibility audits
remain ongoing, without a confirmed interaction claim from that scenario.

Reviewed PR65 (AI chat links restricted to the application origin) and PR66
(operator runbook) are also integrated in merge commits `bcc2c7c` and `30272d5`.
Each independent head passed review and CI; the published f423 combined candidate
now passes its own exact CI, including the Student changes.

### Earlier source23 candidate and preserved failure/blocker

Exact release candidate `23f5ed0ff3ab2c7eddc88a027baaa5729231647c` passed all seven exact-source jobs in
[CI37022756475](https://github.com/jckail/superteacher/actions/runs/37022756475): 1350 API tests, 225 web tests, four browser tests,
84 E2E tests, lint/types/build, Docker/auth smoke and informational benchmark.
The actual Docker-runtime compatibility set passed 259 cases. Reports Summary
freshness is independently reviewed and CI verified: server-cutoff labeling,
scoped forward-day refresh, retained old results/recovery and preservation of
edited parent drafts and pending generation. The combined source also contains
reviewed SMTP breaker corrections and merged theme/copy-feedback/accessibility
changes. Synthetic mail tests passed in the API CI; real SMTP/provider delivery
has not been verified.

Earlier [CI37020532918](https://github.com/jckail/superteacher/actions/runs/37020532918)
failed the Gradebook keyboard test after reload while its last serial score
save was still unconfirmed. The corrected E2E test awaits three distinct successful
assessment/student/points PUT responses before reload, preserving all original
focus, Escape and persisted-value assertions; corrected exact CI passed.

The first operator artifact build `e866d260-390c-4fbb-90d5-c35688966f11` succeeded
at 14:57:45 UTC from immutable archive SHA256
`00f7cf2eb77557a486fcdef2f8cb4c0f4b4dfe0f02d6f2ec809508135b421af1`, producing
`gcr.io/portfolio-383615/superteacher@sha256:66df34171a6ee17ae027840f7945f056471ddcaf01a0e15fea608af96f03a35d`.
Owned staging revision `00008-6cj` failed startup on `/app/litestream.yml`
permission denied: the operator context file had mode 0600. This is an artifact
packaging failure, not failed source CI or an accepted source23 runtime. Failed
image/prefix receipts are preserved; B5 `00007-9lq` remains Ready at 100% with
fresh proof. No production traffic or domain change was made by this operator.

Corrected context `context-b` uses the SAME archive bytes, regular modes 0644/0755,
directories 0755 under private 0700 roots, and a separate `-b` image tag. Independent
source review and 264-file/292-entry content/layout/mode comparisons passed.
Root's protected corrected build session 7798 exited 75 when its queue wait expired.
The helper never started: no build-b intent/proof or cloud call occurred. No corrected
build, staging smoke, recovery or readback success is claimed. Do not retry unchanged after lock exit 75
or bypass the shared wrapper.

Dedicated runtime IAM permission probe passed separately; its protected rehearsal
command exited 75 before the helper/service began. Full runtime acceptance remains
pending; probe success is not a served rehearsal or production identity change.
See [runtime IAM](plans/runtime_iam.md). Student runtime acceptance and independent Insight freshness, draft provenance,
full grading policies/terms/enrollment, real-provider/email evaluation and final
production adoption/drain/rollback/domain cutover remain open.

Remote main subsequently advanced through `3290cc3` (PR19) and `1cde1cc` (roadmap).
Root reviewed/integrated those changes and the pinned 1cde exact CI passed, as recorded
above. The earlier source23 run remains bound to source23; its failed artifact and
exit 75 blocker do not establish a failed or accepted runtime for the new candidate.

Bounded read-only public observation: `www` health/readiness/calendar returned
404, version returned 200 with `development`, and no HSTS was observed. B5 health
and readiness returned 200, version reported full B5 source, calendar returned 401,
and no HSTS was observed. These endpoint observations do not establish broader
production/domain state or acceptance of the pending 9011 HSTS source. Production
changes by another harness remain separately documented.

### Latest root-accepted historical staging release (B5)

Source `b5c1b8d00294afce0ebb5228b3be1c3a423d6191` is pushed to main and the
working branch. Exact-source
[CI37013321634](https://github.com/jckail/superteacher/actions/runs/37013321634)
passed all seven jobs: 1312 API tests without skips/xfails including real
PostgreSQL, 207 web tests, four browser tests, 83 E2E tests, lint/types/build,
Docker/auth smoke and the informational benchmark. Independent backend/client
Overview freshness reviews and focused checks passed. The actual Python 3.12.15
runtime compatibility set remains 259 passing cases.

Overview now returns its captured server `as_of` on every envelope and displays
that cutoff. Its ready-gated client refreshes the exact existing scope query on
validated forward school-day changes, with bounded scope/day attempts, stale
response rejection and explicit failure/manual recovery. Empty and unknown
populations stay distinct. Native means, stable ordering, sentinel 101 and
at most eight retained attention candidates remain unchanged; scalar mean storage
is still O(N), with full population/history scans and existing batch histories.
This does not imply snapshot isolation or immediate midnight freshness.

Protected Cloud Build `42d93f52-189c-43b6-a954-8e243690bda4` succeeded at
13:40:07 UTC from the immutable source archive.
Image: `gcr.io/portfolio-383615/superteacher@sha256:719f06c8f9da2ec4f77dcf97141e88244f4a6bdc289256c46e3f227acf5248b5`.
Ready staging revision `superteacher-overhaul-staging-00007-9lq` serves it at 100%,
with full-SHA VERSION and a verified fresh replica prefix
`overhaul-staging/b5c1b8d00294afce0ebb5228b3be1c3a423d6191-c4cc366433e9`.
AI/demo disabled; max one instance, no minimum. Synthetic HTTP checks passed
creation/transfer/history/raw precision, Overview counts/native precision/cutoff,
class-summary statistics and Gradebook cutoff, scoped header continuations,
Unicode/BOM/CRLF CSV, historical account JSON, parent-update section preflight
and copied-cookie logout. Private credentials and receipts remain outside Git.
Recovery-only execution `superteacher-overhaul-recovery-b5c1b8d-b7l4d`
succeeded at 13:51:10 UTC. The exact image/prefix restored into fresh transient
SQLite and verified integrity, foreign keys, native head `0003`, transfer history,
notes, attendance and both raw extra-credit values. Structured restore proofs
and subsequent staging receipt readback passed; the overridden entrypoint never
starts a server or replica writer. Executed final-image inventory confirms Python
3.12.15, OpenSSL 3.0.22, SQLite 3.40.1 and 40 distributions; all 39 prior observed
package resolutions matched. Metadata at that acceptance checkpoint confirmed native `00006-cjv`,
legacy `00018-t58` and staging `00007-9lq` Ready at 100%. This operator did not change production services or
custom-domain mappings; both public Super Teacher domains were confirmed to
route to `edutrack`. Final writer drain and zero-loss RPO remain unproven.

Next: complete immutable runtime acceptance for integrated Student work; independent Insight freshness and AI snapshot/draft semantics,
full grading policies/terms/enrollment, permitted real-provider evaluation and
final dataset/writer-drain/rollback/domain cutover remain open. Dedicated runtime
IAM resources have been provisioned and a separate permission probe passed, but
the protected rehearsal exited 75 before its helper began; runtime acceptance is pending;
this release does not claim acceptance or production identity changes. The original
unbudgeted overhaul goal remains active.

### Previous verified Overview retention and runtime release

Source `c3277b4ea55617f0adce5521a26422ec54e77b77` is pushed to main and the
working branch. Exact-source
[CI37010699744](https://github.com/jckail/superteacher/actions/runs/37010699744)
passed all gates: 1309 API tests without skips/xfails including real PostgreSQL,
194 web tests, four browser tests, 83 E2E tests, lint/types/build, Docker/auth
smoke and the informational benchmark. Independent reviews and root's 95 focused
Overview regressions passed.

This release retains at most eight Overview attention candidates while preserving
native scalar means, counts, stable ordering, the missing-average sentinel and
full DTOs. Scalar mean storage remains O(N); full population/history scans and
existing batch histories remain. It also pins Python 3.12.15 Bookworm to a verified
base digest. Actual-image checks confirmed Python 3.12.15, UID 10001, imports,
OpenSSL 3.0.22 and SQLite 3.40.1. A disposable constrained pytest environment kept
all 40 production distribution versions unchanged and passed 259 Unicode/security,
account-token, archive and streaming cases. CI's native API runner used 3.12.14.
All 39 prior observed pip-install resolutions matched the CI image inventory;
this is narrower than a full prior executed runtime inventory. See
[runtime maintenance](plans/runtime_maintenance.md) for evidence and limits.

Protected Cloud Build `5ebbab7c-acbf-494d-95c3-9926180ff099` succeeded at
13:14:12 UTC from an immutable Git archive (SHA256
`e40d2e8fcc9cbec8c0c5926936ea10bb9d1cafce91319d39a0a6604b141b2b98`).
Image: `gcr.io/portfolio-383615/superteacher@sha256:0618d422f3daa90b93c5760843d011a5dab29ddb4572e9cca837a664930a35d4`.
Staging revision `superteacher-overhaul-staging-00006-fl2` previously served it at 100%,
with full-SHA VERSION and a verified fresh replica prefix
`overhaul-staging/c3277b4ea55617f0adce5521a26422ec54e77b77-9df38b9db3d4`.
AI/demo disabled; max one instance, no minimum. Synthetic HTTP checks passed
creation/transfer/history/raw precision, Overview counts/native precision,
summary statistics and Gradebook cutoff, cursor/CSV/account exports, parent-update
section preflight and copied-cookie logout. Private credentials/receipts remain
outside Git. Recovery-only execution
`superteacher-overhaul-recovery-c3277b4-hlwcb` succeeded at 13:20:46 UTC.
The exact image/prefix restored into fresh transient SQLite and verified integrity,
foreign keys, native head `0003`, transfer history, notes, attendance and both raw
extra-credit values. Both structured restore proofs and staging receipt readback
passed. The overridden entrypoint never starts a server or replica writer.
Executed final-image inventory confirmed Python 3.12.15, OpenSSL 3.0.22, SQLite
3.40.1 and 40 distributions; all 39 prior observed package resolutions matched.
Fresh metadata confirms native `00006-cjv` and legacy `00018-t58` remain Ready at
100%; production traffic/domain mappings are unchanged. Final writer drain and
zero-loss RPO remain unproven.

At this checkpoint, Overview date freshness was a separate pending slice and
was absent from this pinned artifact. It subsequently passed independent review,
exact CI and staging/recovery verification in `b5c1b8d`, recorded above. Other date
consumers and broader model/production acceptance remain open.

### Previous verified summary and Gradebook release

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
Staging revision `superteacher-overhaul-staging-00005-klh` previously served it at 100%,
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
new-source image build stopped with shared-lock exit 75 before Cloud Build began;
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

The protected build of immutable source `c2812f4` stopped with exit 75 before
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

The protected image build for this source stopped with exit 75 at the shared
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
receipts remain outside Git, mode 0600; values are not included here.

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
was independently read and verified; a local mode 0600 proof is retained at
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
