# Architecture decision records

All five records are **Proposed, needs owner decision**. Written 2026-10-02 against `origin/main` (bb23101) and the live GCP project `portfolio-383615` (read-only). Costs are estimates with stated assumptions; regulatory sections are engineering guidance, not legal advice.

| # | Record | Status | One-line recommendation (monthly cost at 1 / 10 / 100 teachers, estimate) |
|---|---|---|---|
| [0001](0001-persistence.md) | Production persistence | Proposed, needs owner decision | Litestream to GCS with max-instances=1 for the pilot ($0-1 / $1 / $3), move to Cloud SQL `db-g1-small` (about $28) when you pass about 10 teachers or need multi-instance |
| [0002](0002-identity-and-tenancy.md) | Identity and tenancy | Proposed, needs owner decision | Google sign-in with an invite allowlist plus `courses.owner_id` ($0 / $0 / $0); Clerk if you need organisations soon |
| [0003](0003-privacy-and-ai-data.md) | Student privacy and AI data | Proposed, needs owner decision | Pseudonymise prompts, notes off by default, request Anthropic ZDR and a DPA (about $0 infra; 3-5 days work) |
| [0004](0004-grading-policy.md) | Grading policy | Proposed, needs owner decision | Policy objects at section/course/owner level with defaults equal to today's numbers (about $0; 4-5 days for first slice) |
| [0005](0005-domain-cutover.md) | Domain cutover | Proposed, needs owner decision | Staging host `app.` first, then repoint `www` and apex mappings to `superteacher`; no data to migrate (about $0) |

## Recommended path

Production today is not what the repo suggests: `www.the-super-teacher.com` serves the November 2024 "EduTrack" sample-data demo (Cloud Run service `edutrack`, ephemeral database, open unauthenticated API), while the new `superteacher` service is deployed but unreachable on the real domain and, like the old one, loses its SQLite file whenever the container is replaced. So the order is: first make data durable (0001, Litestream, about 1 to 2 days), then add per-teacher accounts and owner scoping (0002, 5 to 8 days) and the AI minimisation and deletion/export work (0003, 3 to 5 days) before any other teacher or any real roster goes in, in parallel with the first slice of configurable grading (0004, 4 to 5 days) because teachers will not trust numbers that differ from their official gradebook. Cut the domain over last (0005): stand up `app.the-super-teacher.com` early for the pilot, and repoint `www` and the apex only when the go/no-go list in 0005 is green (persistence drilled first). Total about 3 to 4 weeks for one engineer; running cost under about $30/month for the pilot.

## Decision table (answer in one reply)

Reply with a line per record, for example `1: Litestream/GCS, 2: Google sign-in, 3: yes + ZDR, 4: first slice, 5: staging first`.

| # | Question | Choices (recommended first) |
|---|---|---|
| 1 | Persistence | (a) Litestream/GCS now, Cloud SQL later; (b) Cloud SQL now; (e) Neon/Supabase; reject FUSE, Filestore, Firestore |
| 2 | Identity | Google sign-in + allowlist; Clerk; other. Also: invite-only pilot or school/org tier now? Which email owns the existing data? |
| 3 | Privacy | Approve pseudonymisation and notes-off default (yes/no); pursue Anthropic ZDR + DPA now (yes/no); engage counsel before any school (yes/no) |
| 4 | Grading | First slice = weights, scale, missing-work, attendance (yes/no); default for missing work in new courses: exclude or zero |
| 5 | Cutover | Staging host first then repoint (C then A); or swap revision of `edutrack` (B). Canonical host: www or apex. Where is DNS managed? Retire `edutrack` after 14 days (yes/no) |

## Open questions for the owner

1. Who has access to the DNS provider for `the-super-teacher.com` (it is not in project `portfolio-383615`)?
2. Is the first audience only you, a few invited teachers, or a school?
3. Budget ceiling per month for the pilot?
4. Do you want to be told about the unauthenticated EduTrack API immediately and take the old site down now, ahead of the cutover?
