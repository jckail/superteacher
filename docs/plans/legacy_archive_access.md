# Retained legacy history access

Proposed follow-up, inspected against native source at `9a8da6a` on
2026-10-02 UTC. This records remaining work; it implements no access feature and
authorizes no disclosure, production ownership change, or deployment. Only
public source and synthetic fixtures were inspected for this plan. Graphify
queries returned paths in other repositories rather than this importer; the
anchors below were verified in current source.

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
