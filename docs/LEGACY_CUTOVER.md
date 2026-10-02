# Legacy public-domain cutover prerequisites

Read-only audit on 2026-10-02 UTC. Project `portfolio-383615`, region
`us-central1`. No deployment, routing, secrets, database records, or cloud
configuration were changed. Public probes recorded HTTP status only. A later
authorized private API archive retained response bodies locally; no roster
response bodies were printed or placed in Git.

## Verified routing and persistence metadata

Both `the-super-teacher.com` and `www.the-super-teacher.com` map to `edutrack`.
Ready, CertificateProvisioned, and DomainRoutable conditions are true. Service
`edutrack` serves revision `edutrack-00018-t58` at 100% traffic with image
`gcr.io/portfolio-383615/edutrack:v0.1.0`.
The ready revision was created on 2024-11-07; its recorded image digest is
`sha256:099dfa822098747f26db0955217e19f5549e9a8bd8f1aa5778bc36aee66af6af`.
The revision permits 100 instances with concurrency 80. A fresh registry image
describe returned not found, so recovery by redeploying this image is unverified.

The service declares no environment variables, secret references, volumes, or
Cloud SQL attachment. This establishes the absence of configured persistent
storage, not the absence of records created by a user. Prior demo-only claims
in ADR 0005 must not substitute for a retention decision.

| Public GET path | HTTP status |
| --- | --- |
| `/api/version` | 200 on apex, www, and the direct edutrack service |
| `/api/overview`, `/api/courses`, `/api/students`, `/api/auth/me` | 404 on all three hosts |
| `/api/health`, `/api/account/export`, `/api/metrics` | 404 on all three hosts |
| `/api/db/classes`, `/api/db/students` | 200 on www without credentials |
| `/openapi.json`, `/docs`, `/api/api/health` | 200 on www |

A 200 health response here does not establish the contents of its health body.
The actual legacy roster paths remain publicly readable. Do not use the newer
`/api/students` path returning 404 as evidence that legacy data is inaccessible.

## Source compatibility

Historical source commit `bbeea0f395a6ec4ebd325ec9e7c3c2de9193045f`, immediately
before the native overhaul, contains:

- `backend/app/models/database.py`: SQLite configuration, `init_db` with
  `Base.metadata.drop_all` and `create_all`, and classes/sections/students tables.
- `backend/app/routers/db.py`: GET `/classes`, `/students`,
  `/students/{student_id}`, `/classes/{class_id}/students`, and
  `/classes/{class_id}/sections`, exposed under the legacy `/api/db` prefix.
- `backend/app/schemas/student.py`: legacy student fields `grade`, `class_id`,
  `section`, `gpa`, aggregate attendance/homework fields, `academic_performance`,
  and `ai_insights`. Sections expose their name and class ID.

This is a historical schema candidate; the exact source of the deployed
`v0.1.0` image remains unproven. There is no corresponding local Git tag.
Historical source restart behavior must not be attributed to the exact serving
image without provenance. Startup sample data also does not prove that no user
has subsequently changed the public write API.

Native baseline `0001` uses courses, sections, students, assessments, scores,
attendance, notes, and insights. The strict baseline validator in
`superteacher/db.py` correctly refuses the legacy classes/aggregate schema.
The offline independently published **accounts 0002** adoption path addresses
a separate native-schema history; it cannot import EduTrack tables. Do not stamp
an EduTrack database as native `0001`, `0002`, or `0003`.

## Concrete cutover blocker and preservation options

Preserve the legacy archive by default under the authorized overhaul scope.
The remaining data blocker is a verified retention/import plan that faithfully
carries its representable records forward and retains unrepresentable historical
aggregates without inventing events. The new candidate's synthetic restore rehearsal
cannot establish preservation of the legacy service's records.

An authorized private archive captured GET `/api/db/classes`, GET
`/api/db/students`, and per-class GET `/api/db/classes/{class_id}/sections` into
a new local file created exclusively with mode 0600 in a directory with mode
0700. Artifact:
`/home/jkail/.local/share/superteacher-backups/legacy-api-20261002T061522.617300Z-dbeb3a3b.json`.
Capture completed at 06:15 UTC. Schema shapes, unique identities, class/section
relationships, and repeated class/student identities and payloads all passed.
The private artifact records original responses, request times, source/version
metadata, per-response hashes, and consistency limits. Its SHA-256 is
`8079ba7624eb1d64dce273056bb4a33e9bcf86c3f43ca4e6ba30c65793131de3`.
Do not print row contents or upload the archive to memory, repository, or public
artifacts. Preservation is an API archive, not a verified live-database backup.

HTTP snapshots are neither transactional nor guaranteed to come from the same
container. Legacy instance-local storage and scaling permit divergent copies;
freezing writes and identifying the authoritative instance/dataset are separate
operator prerequisites. A new instance or redeployment may recreate its data.
A downloaded API archive must therefore be described as an API archive, not a
verified full live-database backup. If direct consistent database recovery is
unavailable, retain this limitation in the operator's acceptance decision.

If migration is required, implement and test an offline adapter against the
archived schema in a new isolated native database. Map each legacy class to an
owned course, resolve sections by class/name, and preserve a stable old-to-new
ID map. Import actual dated nested tests/homework only when their semantics,
score denominators, and dates validate as native assessments/scores. Preserve
aggregate GPA, attendance, homework counters, and old AI output in the private
archive when they cannot be represented faithfully. Do not invent dated
attendance or overwrite native computed grades with aggregate legacy values.
Validate completeness, ownership, duplicates, numeric constraints, and recovery
before adopting the output as a production dataset.

Finally, verify exact image availability and an operational rollback target;
a ready old revision alone is not proof that it can cold-start or redeploy.
Keep existing domain mappings until the retention/import decision, intended
native dataset, writer-drain gate, and rollback plan are verified by the
deployment owner. This document authorizes no cloud mutations or payload export.
