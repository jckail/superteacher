# Legacy import execution

Spec: ../LEGACY_IMPORT_PLAN.md and ../LEGACY_CUTOVER.md. This executes the saved
faithful-import requirement of the original active overhaul, not a production
cutover authorization. Existing native worktree/branch is owned by root; other
harnesses have separate worktrees. Root owns commit/push and verification.

## Global constraints

- Preserve every original archive byte and historical field. Never print private
  records, mappings, email addresses, or SQL parameters; return sanitized errors.
- Source archive is read only and remains outside Git. New artifacts are private,
  no-overwrite, and complete before publication. No live database/cloud mutation.
- No invented assessment/score/attendance/note/AI events from legacy aggregates.
- Explicit owner ID/email inputs; default disabled rehearsal principal. No
  authentication sessions, starter classroom, email or provider requests.
- Native output migrates 0001 -> 0002 -> 0003; validate integrity, foreign keys,
  ownership, source dispositions, empty event/cache tables and unchanged input.
- Root owns expensive verification. Agents run focused checks only, no dependency
  installs/builds/browser/cloud calls. One browser tab per agent if ever needed.
- Query shared Graphify first; missing coverage means inspect live source.
- No child agents from workers. Independent review follows implementation.

## Task 1: Private input schema coverage

Inspect the authorized private archive from LEGACY_CUTOVER.md without printing
records. Write a private schema-only report under /tmp/st-legacy-schema-report.json
(mode0600), plus a concise task report. Describe top-level envelope, response path
selection, known field/type coverage and counts. Never print student names/IDs,
class/section names, nested assignment labels, email or bodies. Verify source hash,
file permissions, stored per-response hashes and repeated-response consistency.
Do not edit source, archive, repository, cloud or database. Supply the adapter
implementer the schema-only format and any constraints that require fail-closed.

## Task 2: Offline adapter and synthetic verification

Own superteacher/import_legacy_archive.py and tests/test_legacy_archive_import.py.
Implement the saved mapping plan as a reusable offline CLI/API. Read a bounded
standalone archive, validate provenance/per-response hashes, select classes,
students and per-class sections without treating repeated responses as new rows.
Strictly reject malformed/ambiguous references, duplicate identities, invalid
native fields, normalization/uniqueness collisions, nonfinite values and changed
repeated response sets. Preserve unknown historical fields in original bytes.
Require expected source SHA256, explicit owner ID/email, and output path; the
principal is disabled by default. Output a single atomic mode0600 no-overwrite ZIP
bundle containing native.db, manifest.json, and the unchanged original archive.
The private manifest binds source hash/schema/capture, importer version, native
head, ownership and stable source-to-native ID maps, all field dispositions and
history limitations. The SQLite DB remains standalone and validated. Use a private
temporary workspace and publish only the completed bundle with no-overwrite link;
leave existing artifacts untouched and clean owned incomplete work on failure.
Reject symlink/path aliases and writable/permissive input if the contract requires
source freezing; provide a documented source preparation path. No printed private
exception values. Report only status/counts/paths. Roster-only output contains no
assessment, score, attendance, note or insight-cache rows. IDs must be stable for
the same source and distinct source identities; reject collisions, never dedupe
students by name. Use actual native schema validation/constraints.

Meaningful focused synthetic tests cover valid faithful mapping, same-name
students, class/section ambiguity, duplicate source IDs, normalization collisions,
invalid grade/text, nonfinite JSON, provenance/hash drift, percentage-only history,
unknown retained fields, no owner guessing, no-overwrite/alias/symlink refusal,
source bytes unchanged, rollback/publication failure, artifact permissions,
integrity/ownership/native0003 and empty event/cache tables. Do not write tests
that merely mirror helper implementation. Finish with Ruff and focused tests.
Commit only owned files after root requests it; initially leave diff for review.

## Task 3: Independent adapter review

Review the implementation against Task2 and its referenced spec; inspect the
actual diff and report evidence. Return separate spec-compliance and code-quality
verdicts, concrete findings with locations, and privacy/atomicity/integrity gaps.
Do not repeat passed tests, edit code, inspect private records, or run cloud/build.
Root sends findings to implementer and requests scoped re-review after fixes.

## Task 4: Exact-archive rehearsal and recovery

Root runs the reviewed adapter against the authorized frozen private source into
an exclusive private output, using an explicitly disabled synthetic principal.
Validate source hash unchanged, accepted roster dispositions, stable mapping,
unknown historical field preservation, native0003/integrity/FK and ownership.
Extract only into private storage; backup/restore the native database into another
new file and compare all rows. No service/traffic/prefix/domain changes. Record
curated counts/status/source hashes/limits in deployment and continuity docs;
no record contents or private mapping in Git or hosted memory. Production owner,
authoritative dataset, final capture/drain and rollback remain separate gates.
