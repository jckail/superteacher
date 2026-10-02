# Retained legacy history access

The initial plan was inspected against native source `9a8da6a` on 2026-10-02 UTC.
The offline viewer and validation API are now implemented; the execution
checkpoint below records the supported contract and synthetic evidence. Real
recipient entitlement, delivery and native authenticated integration remain open.
Graphify returned other repositories rather than this importer, so findings use
current native source. Implementation and review used synthetic fixtures.

## Initial decision

Build an offline operator viewer first. An authorized teacher can request a
specific student's retained history through an operator, who produces a private,
bounded view after checking the approved owner and identity mapping. Self-service
in the native application is a later feature with separate storage, tenancy,
retention, and export/deletion decisions. A disabled rehearsal principal does
not establish which real teacher may receive any archived record.

The initial viewer reads a preserved import bundle without changing it or the
native database. It displays legacy percentage strings and aggregate fields as
historical observations, accompanied by capture provenance and limits. It creates
no assessments, scores, attendance records, notes, or insight-cache rows. Native
grades, metrics, and AI context continue to derive only from native evidence.

## Existing contract to reuse

`superteacher/import_legacy_archive.py` publishes a private ZIP with exactly
`native.db`, `manifest.json`, and unchanged `original_archive.json`. The manifest
contains `source_sha256`, `native_db_sha256`, importer version/source hash,
`native_revision`, capture metadata, `selected_response_indices`, `owner`,
`id_maps`, normalization changes, field dispositions, counts, and limitations.
Student maps preserve distinct source identities even when names match; section
maps use the source class identity and section name. Synthetic coverage in
`tests/test_legacy_archive_import.py` verifies byte retention, distinct same-name
students, stable maps, private permissions, schema head, and empty event tables.
Those assertions do not prove any real teacher's entitlement to the archive.

The manifest is private too: retained JSON pointers can contain assignment
labels, and ownership/mapping/normalization entries contain private information.
Never publish it, place it in ordinary application logs, or treat it as harmless
metadata. Embedded hashes verify consistency but cannot authenticate a bundle
whose archive and manifest have both been replaced. Access requires an approved
external receipt binding the complete bundle digest, source digest, importer
revision, and authorized owner; store that receipt privately and separately.

## Bounded operator viewer

1. Accept explicit private bundle and approval-receipt paths plus an approved
   owner and one native student identity or exact source identity. Supply private
   selectors through a restricted request file rather than command arguments or
   shell history. No name search, whole-roster dump, automatic owner inference,
   login creation, or cloud download in the first version. Validate the request
   against the operator's authenticated authorization record; an owner ID flag
   alone is insufficient authorization.
2. Open read-only, reject symlinks/unsafe aliases, require restricted directories
   and files, and apply bounded ZIP member count, compressed/uncompressed sizes,
   JSON depth/entry counts, and duplicate-key rejection. Require the three exact
   members once each; do not extract arbitrary paths or execute bundled content.
   Validate the externally approved bundle digest, original archive digest,
   captured response body digests and parsed payload agreement, importer/schema
   support, response selection, roster relations, and manifest maps/dispositions.
   Reject missing, contradictory, ambiguous, or unsupported evidence with a
   sanitized error. Reuse the importer's validation semantics without invoking
   its database-writing or publication path.
3. Resolve exactly one source record through the verified manifest and primary
   student response; repeats only establish consistency. Confirm its source
   class/section chain and native mapping. Check the immutable bundled database
   hash and ownership chain read-only. If delivering against an active account,
   separately verify the current account and student/course ownership: the
   initial `native_db_sha256` describes the bundled snapshot, not today's edited
   production database. Refuse deleted, transferred, or unresolved identities
   until their retention/access disposition is explicitly approved.
4. Create one new, exclusive private output file (0600 in a 0700 directory),
   never overwrite an existing report. Prefer plain UTF-8 text with control
   characters visibly escaped; preserve exact original bytes in the source
   archive. Do not print record contents to the terminal. If a local HTML view
   is later chosen, escape every label/value, prohibit scripts, remote assets
   and links, and avoid a web server. Keep output bounded; oversized or unknown
   shapes require a reviewed private continuation rather than silent truncation.
5. Show the selected student's retained `academic_performance.tests` and
   `.homework` labels/percentage strings, plus explicitly requested aggregate
   fields. Explain that labels need not identify distinct events, dates and raw
   score denominators are unavailable, and the non-atomic capture may omit later
   writes or divergent instances. Show capture time as capture time. Native
   identity mapping is provenance, not proof of legacy account ownership.
   Keep old `ai_insights` and unknown fields retained but excluded from the
   initial view; any later raw-field view requires an explicit scoped decision.
6. Record a private access audit with approved actor, authorization reference,
   bundle/source digest, selected identity, disposition and time. General logs
   contain counts/status only. Define private output delivery, expiration and
   cleanup before real use; never email, upload, copy into AI prompts, or publish
   a report automatically.

## Later authenticated attachment

If direct teacher access is approved, introduce a separate archive attachment
and owner/identity linkage rather than widening the existing student schema or
placing archived values in notes/insights. Keep source artifacts in private
storage outside frontend assets and public object paths. Every lookup must join
the authenticated current owner through the native course/section/student chain
and the approved attachment mapping; knowledge of an ID or storage key grants
no access. Use a dedicated, bounded history response with `Cache-Control:
no-store`; prohibit shared caches, analytics payloads, service-worker storage,
and raw archive/manifest download in the initial UI. Treat labels as untrusted
text and show historical provenance beside values.

Add no archive lookup to `superteacher/ai.py` context builders or
`superteacher/ai_tools.py` tools. Add no fields to native metrics or insight
fingerprints. The existing account export and `purge_user` in
`superteacher/routers/account.py` handle native rows only; they presently provide
no external-archive lifecycle. Before attachment release, decide whether archive
history is included in scoped account export, how access is revoked on student
transfer/deletion, and how account deletion affects access links, private outputs,
backups and retained originals. Retention exceptions must be disclosed and
authorized, not implemented as silent deletion or permanent access.

## Evidence and decisions needed

- Approve the real owner and recipient, source dataset/capture limits, identity
  reconciliation, and who may operate the viewer. Preserve authoritative-source
  and deployed-image uncertainty from `../LEGACY_IMPORT_PLAN.md` and
  `../LEGACY_CUTOVER.md`; a source candidate commit is not deployment proof.
- Establish the private approval receipt, trusted digest source, custody,
  delivery channel, retention period, revocation and deletion rules. The current
  manifest supplies mappings and consistency evidence, not a signed access grant.
- Implement the viewer and focused synthetic tests: duplicate names, wrong
  owner, missing/duplicate mapping, transferred/deleted student, modified archive
  or manifest, forged internal hashes, response drift, unknown fields, hostile
  labels/control characters, ZIP bombs/path traversal, no-overwrite output and
  private permissions. Prove percentage strings remain historical and all native
  event/metric/cache data stays unchanged; assert output/log/provider separation.
- Rehearse privately only after authorization; verify selected-record fidelity,
  audit/delivery/revocation, artifact immutability and recovery. Report sanitized
  counts and checks. Self-service attachment additionally needs cross-account
  API tests, cache/frontend/AI exclusion checks and export/deletion verification.

Next work item: approve the operator viewer's authorization and delivery contract,
then implement against synthetic bundles. Existing archive preservation and
roster import do not yet provide teacher-facing historical access.

## Synthetic operator viewer execution slice

Implemented first offline slice in `superteacher/view_legacy_archive.py` with
`tests/test_legacy_archive_viewer.py`. Development used invented captures only;
no real approval receipt, private archive, student history output or delivery was
created. The importer, native schemas/metrics/AI and archive bytes are unchanged.

Invocation:

```text
python -m superteacher.view_legacy_archive --request-file /private/request.json \
  --expected-bundle-sha256 <externally-approved-bundle-sha256> \
  --expected-receipt-sha256 <externally-approved-receipt-sha256>
```

A restricted version-1 JSON request contains `bundle_path`, `receipt_path`,
new `output_path`, new `audit_path`, `owner_id`, `aggregates`, and exactly one
`source_student_id` or `native_student_id`. All paths are absolute; the request
and frozen bundle/receipt are operator-owned mode0400 standalone regular files
inside mode0700 immediate directories. Ancestors may have ordinary directory
permissions but cannot contain symlinks. Reads/publication are directory-fd
anchored; symlinks, hardlink aliases, FIFOs and existing output/audit are refused.

The version-1 receipt binds `authorization_reference`, `actor`, `operator_uid`,
`recipient_reference`, `approved_at`, `expires_at`, `bundle_sha256`,
`source_sha256`, `importer_version`, `importer_sha256`, `native_revision`,
`owner_id`, `native_student_id`, `source_student_id`, `source_class_id`,
`source_section`, `aggregates`, `purpose`, `identity_disposition` and
`retention_delivery_reference`. Purpose must be `operator_history_review` and
supported disposition `verified_archive_review`; deleted/transferred/unresolved
or active-account delivery dispositions are unsupported and refuse. Approved
actor UID must equal the local operator, scope must match exactly, and the time
window must be current. Only importer v1 at reviewed source hash
`79784f1179f71be2772affadc1539ec56ee5f420c7f50d9a192434c9e06f6f37`, schema
`reviewed-edutrack-public-api-v1` and native revision `0003` are supported.

These digests must come from an independently authenticated approval channel.
The tool does **not** authenticate an operator-created receipt or establish real
teacher entitlement. Snapshot owner/mapping checks do **not** prove current
production ownership. Real operation still requires the approved actor/recipient,
trusted approval custody, identity disposition and delivery/retention procedure;
this development result does not resolve those decisions.

The report contains one selected student's original test/homework string values,
visibly escaped untrusted text and capture/mapping provenance, with explicit
absence of dates/raw points/denominators. No aggregate is shown by default;
request/receipt allowlist supports `gpa`, `academic_performance.rank`,
`attendance_percentage`, `attendance_days`, `homework_points`,
`homework_completed`. Missing/null are distinct. Unsupported history/aggregate
shapes refuse. AI insights and unknown fields remain retained but excluded.

Bounds: bundle <=128MiB; request/receipt <=64KiB each; exactly three regular ZIP
members (`native.db` <=64MiB, `manifest.json` <=32MiB, original archive <=32MiB),
total expanded bytes <=128MiB; JSON depth <=64 and cumulative <=1,000,000 nodes
including separately parsed response bodies; report <=256KiB. Duplicate keys,
nonfinite numbers, unsupported ZIP encodings/layouts, evidence contradictions
and oversized inputs refuse without truncation. Parsing allocations and SQLite
work remain bounded by inputs rather than a general RSS guarantee. SQLite VM
progress budget is 20 million instructions for the connection's validation work.

Full manifest derivation reuses only importer validation helpers; the viewer never
runs import/migration/publication paths. Database bytes are placed in a new private
temporary file, opened immutable/read-only with trusted schema disabled, checked
for supported tables/columns, no views/triggers/virtual tables, integrity/FKs,
exact roster/owner and empty event/auth/usage tables, then removed. Unexpected
schema versions refuse. Source bytes are rechecked before publication.

Report/audit mode0600 outputs are exclusive. Audit first records pending
publication and the scoped private access reference/digests. Report publishes by
exclusive link, then audit records local publication (not delivery). A crash may
leave pending audit requiring operator reconciliation; two files are not one
atomic transaction. Interrupted/failed publication never overwrites an existing
file or silently claims delivery. stdout contains only status/counts; errors do
not echo paths/selectors/content. No network, browser, provider or automatic
copy/delivery occurs. Native integration/export/delete/retention remains backlog.

Development evidence: initial acceptance failed with missing viewer module, then
passed after implementation. Final focused command
`/tmp/st-resume-python/bin/python -m pytest tests/test_legacy_archive_viewer.py -q`
reported **57 passed in 14.83s**. Owned-file Ruff check and format check passed.
Coverage includes duplicate names/exact native selectors, history/null/Unicode,
external digest pins, wrong/expired scopes, unsafe permissions/links/FIFO,
contradictory manifests/responses, ZIP layout/CRC/size failures, JSON body guard
before recursive importer calls, control escaping/report limits, altered database
rosters/views/triggers/events, immutable read-only enforcement, no network calls,
exclusive publication races/temp cleanup and content-free CLI output. Existing
importer code was not edited or its suite rerun. Root owns independent review,
broader integration checks and shared Graphify refresh before release.

A separate Python API `validate_bundle(bundle_file, *, expected_bundle_sha256,
expected_source_sha256, expected_owner_id)` reuses evidence validation and
returns only status/roster counts without any receipt, student selection, report
or audit. It grants no history access and does not prove recipient entitlement.
This permits an authorized custodian to assess bundle compatibility without
fabricating a real-data grant; the CLI remains grant-required and unchanged.
Root subsequently validated compatibility against the preserved private rehearsal
bundle using a new frozen private copy, independently recorded bundle/source
hashes and the explicit snapshot principal from the prior operator note. It
passed: 11 courses, 33 sections and 30 students; original bytes unchanged and
temporary copy removed. No grant, report, audit or delivery was created. This is
compatibility evidence, not real recipient entitlement or current production
ownership. Private content and proof remain outside Git. Root's fresh 57-case
synthetic run passed in 13.77s after final independent spec/quality approval.
Its synthetic test deletes the receipt, verifies no output/audit/temporary
artifacts, and rejects an incorrect snapshot owner. No real bundle was validated
during development.

Independent review repairs: bundled courses now compare complete roster rows
including each explicit owner ID, so NULL ownership cannot bypass a SQL inequality
count. Both viewer/validation evidence paths require the importer's 12-character
alphanumeric owner contract and a nonempty normalized owner-email string. Database
compatibility additionally pins every reviewed table/index SQL definition with
canonical schema digest
`63db03652786bc231455830870cbf6a9cab85eb8ec18e62067b7f8bd7e8f335c`.
Canonicalization preserves column ordering and all types/nullability/constraint/
index expression tokens and quoted literal contents; only outside whitespace
and independent top-level constraint ordering normalize, because legitimate
SQLAlchemy migration runs can vary constraint order. Unsupported schema layouts
require a separately reviewed additional baseline, never migrations during view.

The pending audit's containing directory is fsynced immediately after the audit
file's content fsync and before report publication, including when output/audit
use distinct directories. Synthetic red evidence: all six repinned forged schema
variants (NULL owner, type/nullability/FK/check/index drift), separate-directory
audit durability, and both common owner-contract cases failed prior code. Final
57-test focused suite passes; owned Ruff check/format check pass. A canonicalizer
regression confirms constraint reordering normalizes while quoted literal content
and type changes remain distinct. No real artifacts were accessed during repairs.
