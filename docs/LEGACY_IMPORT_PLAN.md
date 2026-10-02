# Offline EduTrack roster import and historical archive plan

Implemented offline adapter at `8291cae`, verified on 2026-10-02 UTC.
`superteacher/import_legacy_archive.py` and its 54 focused synthetic tests have
independent spec/quality approval. Root privately rehearsed the exact authorized
archive, then backed up and restored its converted database. No production
database, service, prefix, traffic, or domain configuration changed. Graphify
returned other repositories; live native source supplied the coverage gap.

The input is the private, non-atomic API archive described in
[LEGACY_CUTOVER.md](LEGACY_CUTOVER.md). Preserve its original bytes and hash.
This plan preserves representable roster records in native tables and retains
all original historical fields in the private archive. It does not claim a
lossless gradebook conversion or a complete legacy database backup.

## A source limitation that controls the mapping

Historical commit `bbeea0f` exposes a grade submission with `testName`, `score`,
`totalPoints`, `date`, and `gradeType`. However, `add_grade` in
`backend/app/routers/db.py` persists only a **rounded percentage string**, keyed
by assignment name, in `academic_performance.tests` or `.homework`. The date and
original numerator/denominator are not persisted by that function. Reusing a
name overwrites its previous value. The API's submission schema therefore does
not prove that its GET response retains actual dated score events.

Exact deployed-image source provenance remains unverified. Before using
an adapter with another capture, inspect its schema privately without printing
records, and report only field/type coverage. If nested entries really
contain additional event evidence, validate that evidence separately. A label
and percentage alone cannot establish native `max_points`, `points`, or
`due_date`. Neither a 100-point denominator nor the capture date is an acceptable
substitute.

## Concrete field mapping

| Legacy field or identity | Native representation | Required rule |
| --- | --- | --- |
| `classes[].id` | Private map to `Course.id` | Allocate a valid unique 12-character ID; retain the source ID in the private manifest. Never match courses only by their display name. |
| `classes[].name` | `Course.name` | Validate native text rules and length 120; surface normalization changes and uniqueness collisions before writing. |
| No teacher/account identity | `Course.owner_id` referencing `User.id` | Supply an explicit approved target principal. Legacy public availability is not permission to distribute the dataset to every account. |
| Per-class section `name`, `class_id` | `Section.name`, `Section.course_id` | Resolve by source `(class_id, section name)`; native name limit 60 and uniqueness within course apply. The legacy section API does not provide a stable section ID. |
| Student `id` | Private map to `Student.id` | Preserve each distinct source identity, including students with identical names. Do not use the existing name-based CSV import to deduplicate these records. |
| Student `name` | `Student.name` | Validate native text rules and length 120; preserve the original value in the archive. |
| Student `grade` | `Student.grade_level` | Require an integer from 1 through 12; do not round, clamp, or replace an invalid value. |
| Student `class_id`, `section` | `Student.section_id` through the section map | Require an unambiguous captured class/section relationship. Do not silently create a guessed section or merge similarly named sections. |
| Student `gpa` and `academic_performance.rank` | Original private archive only | Native GPA/risk derives from scores under native policy; do not write an aggregate grade or rank into native computed results. |
| `academic_performance.tests`, `.homework` containing percentages | Original private archive only | Keep every available label/value and provenance. No `Assessment` or `Score` without independently supported date, raw points, denominator, category, and section association. |
| `attendance_percentage`, `attendance_days` | Original private archive only | Do not infer individual dated `AttendanceRecord` rows, excused days, or late arrivals from totals or percentages. |
| `homework_points`, `homework_completed` | Original private archive only | Aggregate counters do not establish native assignments, missing submissions, denominators, or deadlines. |
| `ai_insights` | Original private archive only | Do not load old generated content into `InsightCache`: no verified native fingerprint, model, or generation time exists. Do not turn it into a teacher-authored `Note`. |
| Missing legacy creation dates | Private manifest records import time | Native `User.created_at` may describe creation of a new native principal; it must not be presented as a recovered legacy account date. No artificial note/insight timestamps. |
| No legacy authentication identities | No imported sessions, login tokens, quotas, or global budgets | Start authentication and usage records independently; do not synthesize access grants from a roster. |

Current sources: `superteacher/models.py`, `superteacher/schemas.py`,
`superteacher/metrics.py`, and `superteacher/routers/roster.py`. Native course
uniqueness uses the database's `lower(name)` expression per owner, and sections
are unique by `(course_id, name)`. Validate with the actual target database's
semantics. Names require trimmed, nonblank text and native normalization/control
character handling. Preserve originals; never silently truncate, scrub, merge,
or rename an archival identity to make constraints pass.

A roster-only import creates no assessments, scores, attendance, notes, or
insight-cache rows. Native grades, GPA, attendance rate, and homework rate remain
unknown where no real native events exist. Native risk defaults describe the
absence of native evidence; they must not be advertised as confirmation of the
legacy student's historical standing.

## Private artifacts and importer contract

Keep the source archive, a mapping manifest, quarantine report, and output
SQLite database outside Git in a directory with mode 0700; create files with
mode 0600 and exclusive names. Never emit student names, IDs, note content, raw
HTTP bodies, SQL parameter values, or private mappings to logs, memory, CI, or
published documentation. Operator output should contain status, counts, and
artifact locations only.

The private manifest must bind the source archive hash, capture metadata,
selected primary response set, importer version, target schema revision and
owner mapping to every imported source identity. Include normalized-field
changes, source-to-native course/section/student IDs, and a disposition for every
remaining field. Preserve unrecognized fields verbatim in the archive and flag
them for review; do not drop them from the retention accounting.

Write only to a newly created isolated database migrated through the native
`0001 -> 0002 -> 0003` chain. The existing
`superteacher/adopt_accounts_snapshot.py` repairs independently published native
accounts `0002`; it is **not** an EduTrack adapter. Do not stamp, alter, attach for
writes, or run native migrations against the original EduTrack dataset/archive.
Do not repurpose a production Litestream prefix for rehearsal.

Require the target owner mapping as input rather than guessing from names or
creating a login. An offline rehearsal may use an explicitly marked disabled
synthetic principal; that does not establish production ownership. Create no
starter classroom and send no email. Import the planned roster in one
transaction after all validation passes. On failure roll back and leave no
published partial output. Publish a finished new artifact exclusively only
after integrity checks; never replace an existing destination.

Retain a stable ID map for the whole run and reject collisions. Re-running the
same source into an existing destination should be refused initially; rehearse
into a new database instead. This avoids claiming idempotence before duplicate
and manifest reconciliation are implemented and tested.

## Validation and staged rehearsal

1. **Verify input and provenance.** Check the recorded archive hash, file
   permissions, exact response selection, status/type coverage, and recorded
   consistency checks. Do not treat the repeated responses as independent
   records to import. Record that the archive is non-atomic and not guaranteed
   to represent every legacy instance or later write.
2. **Produce a private dry-run manifest.** Validate shapes, duplicate source
   identities, class membership, exact section resolution, native text and
   numeric constraints, normalization collisions, and ownership. Account for
   every original field as imported, retained historically, or quarantined.
   Unknown or invalid fields cannot silently disappear. Block publication until
   every roster exception has a reviewed disposition.
3. **Implement and verify with synthetic fixtures.** Cover duplicate names,
   section ambiguity, ID collisions, Unicode normalization, invalid grades,
   oversized/control-bearing text, missing relations, percentage-only grades,
   unknown fields, interrupted writes, and destination-exists refusal. Fixtures
   must demonstrate that aggregate history never becomes fabricated events.
   Implemented synthetic coverage passed: 54 focused tests, including
   exclusive publication, read failures, FIFO refusal, and legitimate access-time
   updates.
4. **Rehearse offline.** Run the adapter against the authorized archive into a
   new restricted database. Verify source bytes/hash unchanged, native schema
   head `0003`, `integrity_check`, `foreign_key_check`, uniqueness and all
   ownership chains. Check that imported roster counts match the accepted
   source dispositions and that historical fields remain retrievable from the
   archive through the private identity map. For roster-only conversion, assert
   the five event/cache tables above are empty.
5. **Verify native behavior without external providers.** On the isolated
   output, confirm the intended principal sees its mapped roster, another
   principal sees none, exports contain only owned rows, and self-service
   deletion removes only the selected account. Confirm computed metrics do not
   contain imported aggregate claims. Run with demo seeding disabled and no
   mail/AI credentials; authentication must use explicitly supplied local test
   sessions. Deployment and restore checks belong to the root verification
   owner and require their own resource coordination.
6. **Rehearse recovery.** Produce a private standalone backup of the converted
   output and restore into another new file; verify schema, complete native
   row/hash comparisons, integrity, ownership, and private-manifest linkage.
   Retain the original API archive regardless of whether grades are convertible.
7. **Prepare promotion evidence.** Supply curated counts/status, exact source
   and output hashes, importer commit, field-disposition totals, target ownership
   decision, backup/restore result, known history limitations, and a rollback
   plan. No production prefix, service, traffic, or domain mapping changes are
   part of the offline import. The deployment owner handles the writer-drain
   and promotion gates after this evidence exists.

## Evidence still needed

- Exact source/image provenance for the serving legacy revision, or explicit
  acceptance of a validated observed schema with historical-source limitations.
- Independent evidence of original points, denominators, dates, assignment
  identity, and category. Private schema inspection passed 18 checks and confirmed
  224 test and 167 homework entries are percentage strings without those events.
  Historical source demonstrates those details can have been irreversibly lost.
- Approved target principal and authority to expose retained legacy records to
  that account; account ownership cannot be recovered from the legacy API.
- A policy for inaccessible or unrepresentable history. The default here is
  preservation in the private archive, not destruction or invented events.
- Final production dataset selection/merge and owner mapping. The implemented
  adapter and exact-archive recovery rehearsal below establish offline conversion
  only; they do not adopt records into production or merge an existing native
  dataset.
- A final capture/write-freeze decision and acceptance of instance/temporal gaps;
  existing API snapshot consistency checks do not prove full DB completeness.
- A recoverable rollback service/image. The old revision being ready does not
  prove its missing registry image can be redeployed or cold-started.

## Verified offline conversion checkpoint

The CLI requires an expected source SHA256, explicit owner ID/email and a new
output path. The owner is disabled by default. For Linux/WSL rehearsal, freeze a
separate source copy with mode 0400 inside a mode 0700 directory; the original
archive remains untouched. Publication is a new mode 0600 ZIP with exactly
`native.db`, `manifest.json`, and byte-identical `original_archive.json`. Native
IDs are deterministic for the exact source hash and source identity. The private
manifest binds the importer-file hash, original hash, database hash, identity
maps, normalization changes, and field-retention dispositions. It stays outside
Git and hosted memory.

Root independently verified 11 courses, 33 sections, and 30 students; native head
`0003`, integrity, foreign keys, all ownership chains, the disabled synthetic
principal, unchanged source bytes, and zero event/cache/auth/usage rows. Backup
and restore preserved all native rows. A read-only check using source `9a8da6a`
confirmed all 30 students have unknown metrics/risk and a foreign owner sees zero
rows; the database bytes stayed unchanged. No historical percentage was presented
as a native assessment or score.

Source SHA256: `8079ba7624eb1d64dce273056bb4a33e9bcf86c3f43ca4e6ba30c65793131de3`.
Importer SHA256: `79784f1179f71be2772affadc1539ec56ee5f420c7f50d9a192434c9e06f6f37`.
Bundle SHA256: `133213d35e07aa5e9d5658b80b6d213eb2ea92dba0fce5a15cf07e4ba08fc3c9`.
Private local bundle:
`/home/jkail/.local/share/superteacher-backups/legacy-import-rehearsal-wzx1pde3/native-roster-bundle.zip`.
Private independent proof: `/tmp/st-legacy-import-rehearsal-proof.json`. The
original archive has a verified private versioned GCS roundtrip, described
in LEGACY_CUTOVER.md. The converted bundle also passed a no-overwrite upload
and byte-hash roundtrip in the same bucket, with public-access prevention,
uniform bucket-level access, versioning and no public IAM principals verified.
Bundle URI: `gs://portfolio-383615-superteacher-litestream/legacy-import-bundles/native-roster-8291cae-133213d35e07aa5e.zip`;
generation `1790931240579136`.

The capture remains non-atomic, historical event evidence remains unavailable,
and synthetic rehearsal ownership is not a production ownership decision. A
final capture/freeze, recoverable rollback, preservation of the existing native
dataset, writer drain, and an immutable validated serving image remain required
before domain cutover.
