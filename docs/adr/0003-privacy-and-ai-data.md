# ADR 0003: Student privacy and AI data handling

- Status: Proposed, needs owner decision
- Date: 2026-10-02
- Deciders: Jordan Kail (owner)
- Not legal advice. Everything under "Regulatory considerations" is engineering guidance. **Confirm with counsel before onboarding any school or collecting data about students under 13.**

## Context

Super Teacher holds names, grade levels, scores, attendance and free-text teacher notes for K-12 students, and sends parts of it to the
Anthropic API for chat, per-student insights and parent-email drafts. This ADR records what is sent today (from the code at origin/main,
commit bb23101, 2026-10-02), what Anthropic retains, what the browser stores, what deletion/export exists, and proposes a minimisation plan.

### What leaves the system today (exact fields)

All AI traffic goes server-side to `api.anthropic.com` from `superteacher/ai.py` and `reports.py` using `ANTHROPIC_API_KEY` (Secret Manager
`anthropic-api-key`). Models by default (`config.py`): chat `claude-sonnet-5-5`, insights and parent drafts `claude-haiku-5-5`. All free text passes
through `ai_tools.clean()` (control characters stripped, `<`/`>` defanged, truncated) to blunt prompt injection; it does not remove personal data.

1. **Chat system prompt, roster snapshot** (`ai.build_context_parts`, rendered by `ai_tools.student_line`), sent on every chat turn (prompt-cached):
   for each student when the roster has at most 60 students (`chat_roster_cap`), otherwise per-section summaries plus up to 60 flagged students:
   - full student name (max 80 chars), internal student id (12 hex chars), grade level
   - course name and section name
   - average %, letter grade, trend (points), attendance %, homework %, missing-assignment count, risk status (`on_track|watch|at_risk`)
   - today's date.
2. **Chat focus block** when the teacher is viewing a student (`student_block`): the line above plus risk reasons ("Attendance 78%"), absences, tardies,
   **every score** (due date, kind, assignment title, points/max or MISSING) and the **five most recent teacher notes (date and body up to 400 chars each)**.
3. **Chat tool results** (`ai_tools.py`, each capped at 12,000 chars): `find_students` returns up to 25 rows (id, name, grade, course, section, average, letter,
   trend, attendance, homework, missing, status, risk flags); `get_student` returns the full student block (up to 15 scores, 5 notes); `class_stats` returns aggregates only (section labels, counts, no names).
4. **The teacher's chat messages** (up to 4,000 chars each, last N turns, held in memory per WebSocket in `routers/ai.py`, never stored server side). Teachers can type anything into these.
5. **Per-student insight** (`ai.ai_insight`): the full student block (name, id, grade, course/section, metrics, all scores, 5 notes) to the insight model. The generated card (headline, items; may repeat the name) is **cached in the database** (`insights.payload`).
6. **Parent update draft** (`reports._context`, `PARENT_PROMPT`): student **first name only**, course name, average, letter, trend, attendance %, absences, tardies, homework %, missing count, the **last 6 assessments** (title, kind, score) and **up to 3 notes (300 chars each)** wrapped as untrusted. No parent name, email or phone is in the data model or the prompt. The draft is returned to the teacher; the UI offers only a `mailto:` link (`web/src/pages/Reports.jsx`). The server never sends email.

Not sent because they do not exist in the schema: date of birth, address, student/state ID, demographics, special-education/IEP/504 status, discipline records, photos, parent contacts, free/reduced lunch.

**The real exposure is free text**: notes, assignment titles, course/section names and the teacher's own chat messages are unconstrained. A teacher writing "has an IEP, dad lost job" into a note sends it to the API with the student's name. The prompts instruct the model not to speculate about home life or disability; that does not stop the data from being sent.

### Retention at Anthropic (read 2026-10-02)

- Anthropic's commercial retention article states API inputs and outputs are automatically deleted within 30 days, with exceptions (Usage Policy enforcement, legal compliance, features with longer retention such as the Files API, and custom agreements incl. ZDR). Content flagged by automated safety systems can be kept up to 2 years and trust and safety scores up to 7 years (https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data).
- The API data-retention page says Anthropic does not train on retained data without express permission and that conversation content is "not retained by default" except for "Covered Models" (Claude Fable 5 / 5.1, Mythos 5 / 5.1) that require 30-day retention (https://platform.claude.com/docs/en/manage-claude/api-and-data-retention). The two pages describe the default differently (30-day deletion versus not retained); treat the safe reading as "up to 30 days" and ask Anthropic to confirm in writing.
- **Zero data retention (ZDR)** is a contractual arrangement obtained through Anthropic sales, enabled per organisation: prompts and responses are not stored at rest after the response, except where needed for law or Usage Policy enforcement. Not ZDR-eligible: Message Batches (29-day retention), code execution, Managed Agents, Files-API style features; prompt caching, streaming and tool use on `/v1/messages` are eligible. Covered Models are excluded from ZDR. **The models this app uses by default (Sonnet 5.5, Haiku 4.5) are not on the Covered Models list** as of the page read today, so ZDR would apply, but the list changes; pin the check in the release process.
- ZDR does not delete the Cloud Run request logs or our own database; it only affects Anthropic's storage.
- Anthropic's HIPAA readiness arrangement is irrelevant to FERPA, but shows the self-serve Console route for organisation-level data settings.

### What the browser stores

- Cookie `st_session`: signed, HttpOnly, SameSite=Lax, 12 h; contains no student data.
- `localStorage`: `st-theme`, `st-scope` (selected course id and section id; opaque ids, no names) (`web/src/App.jsx`, `scope.jsx`).
- `sessionStorage` key `st-chat`: **the last 60 chat messages in clear text, which include student names and metrics** (`web/src/components/Chat.jsx`). It is per tab and cleared when the tab closes, but it survives reloads and sits on shared or school-issued laptops until then. There is no logout hook that clears it (check `auth.jsx`).
- React Query keeps API responses in memory; CSV gradebook export is a file download the teacher controls.
- Responses carry `Cache-Control: no-store` for `/api/*`.

### Deletion and export that exist today

- `DELETE /api/students/{id}` cascades to scores, attendance, notes and the cached insight (`ondelete=CASCADE`, ORM cascades).
- `DELETE /api/assessments/{id}`. There is **no** endpoint to delete a course, a section, a note, or an account, and no per-student or whole-teacher data export (only the gradebook CSV). Importing re-creates students by name.
- **Backups defeat deletion**: whichever persistence option ADR 0001 selects keeps copies (Litestream snapshots/WAL retention, Cloud SQL backups and PITR). A deletion promise must state that backups roll off within a fixed window (for example 30 days).
- Cloud Logging may contain stack traces (`log.exception` in `ai.py`, `reports.py`, `routers/ai.py`). Verify no prompt text or note body reaches logs; today only exception types and student ids are logged (`log.warning("cached insight for %s ...", s.id)`).

## Regulatory considerations (engineering guidance, confirm with counsel)

- **FERPA** (20 U.S.C. 1232g; 34 CFR Part 99): applies to schools and districts receiving federal funds; student grades and attendance are education records. A vendor can receive them under the "school official" exception only if it performs a service the school would otherwise do itself, is under the school's direct control for that data, and uses it only for the authorised purpose. In practice schools require a data-privacy agreement (DPA). A teacher entering a whole class into an unapproved third-party tool is a common compliance problem for the teacher and district, not just the vendor. Product consequences: no secondary use or sale, no model training, deletion on request, a place to point schools at (privacy policy, DPA template, sub-processor list that names Google Cloud and Anthropic).
- **COPPA** (16 CFR Part 312): applies to operators collecting personal information from children under 13. In education, the FTC allows schools to consent on behalf of parents when the data is used only for the school's educational purpose, not commercial purposes. The FTC's amended COPPA Rule was published 2025-04-22, effective 2025-06-21, with compliance required by **2026-04-22** (already past): it requires a written data-retention policy, a written information-security program, and separate verifiable parental consent for non-integral third-party disclosures (https://perkinscoie.com/insights/blog/ftc-finally-publishes-amended-coppa-rule-compliance-deadlines-set). Note that students do not use Super Teacher themselves; teachers enter their data. Whether COPPA applies to an app where only adults log in is a question for counsel, but plan to the stricter reading.
- **State student-privacy laws** (more than 40 states; the strictest matter first): California SOPIPA and AB 1584 (no targeted advertising or profiling, no sale, deletion on school request, reasonable security), New York Education Law 2-d (parents' bill of rights, contractor data-security plan, encryption in transit and at rest, breach notification), Illinois SOPPA (written agreements, public listing, deletion and breach duties), Colorado, Connecticut, Texas and Utah student data acts. Many require breach notice inside tight windows (days to 60 days) and a signed state DPA (the Student Data Privacy Consortium NDPA is a common template). Budget for a standard DPA and a sub-processor list.
- **Teachers' own obligations**: district AI policies may forbid pasting identifiable student data into AI tools; give the teacher an easy, visible way to use the app without sending names (minimisation plan below).
- **Anthropic side**: confirm in writing that your Anthropic organisation has accepted the commercial terms with a data processing addendum, that a children's-data use case is permitted under the usage policy, and ask for ZDR.

## Options

1. **Status quo plus disclosure** (privacy policy, DPA, "AI sends names and notes to Anthropic" notice). Cheapest. Leaves names, notes and free text in the prompt.
2. **Pseudonymise prompts (recommended)**: tokens instead of names, notes excluded or scrubbed, rehydrate for display. Moderate work, big reduction in exposure, retains most AI value (analysis is on numbers and patterns).
3. **Local-only AI** (no external model): not practical for the quality required; rejected.
4. **Disable AI for any roster flagged under-13**: simple switch, useful as a school-level setting, but removes the product's differentiator. Keep as a per-course toggle ("AI off").

## Data-minimisation plan (Option 2)

1. **Pseudonymous student tokens.** For each AI request build a per-request map `student.id -> token` where `token = "S" + base32(HMAC(tenant_key, student.id))[:5]` (stable across a conversation so caching and follow-up questions work, meaningless to the provider). Prompt lines become `- S4K2Q (id S4K2Q, gr 8, Algebra 1 / Period 3): avg 71% C-, ...`. Tool arguments from the model use tokens; `ai_tools.execute` resolves tokens back to ids server-side. `find_students(name_contains=...)` runs server-side on real names so the teacher can still ask "how is Maya doing?" (the teacher's message is the only place the real name appears; see 3).
2. **Rehydration** in the streaming path: replace tokens in assistant deltas with the real name before sending to the browser. Because the server holds the map and the response arrives in chunks, buffer a trailing partial token (token length is fixed, so hold back up to 5 characters). The browser never needs the mapping. Persist only the rehydrated text in the browser (and see below).
3. **Teacher messages**: before sending, replace any exact roster name (full or first name, case-insensitive, word boundary) found in the teacher's message with its token, using the same map. Add a UI hint "Names are replaced before leaving the server". Free text outside the roster (a parent's name, a school) is not scrubbed; show a one-line caution under the chat box.
4. **Notes**: default to **not sending notes** to the model. Provide a per-teacher switch "Include my notes in AI" with a warning, and when on, scrub roster names and emails/phone numbers with regexes and truncate to 200 chars. Never send more than the 3 most recent notes.
5. **Parent drafts**: send a placeholder first name (`{FIRST_NAME}`) and fill it in server-side after generation. The rest of the data (metrics, assessment titles) is already low-risk. Keep notes out unless the teacher opts in.
6. **Course/section/assessment titles**: sent as-is (they rarely identify a person); cap length; no school name is in the model.
7. **Insight cache**: store the insight with tokens, rehydrate on read, so a cached payload does not hold names in an unusual place; invalidation fingerprint (`metrics.fingerprint`) already hashes the name, keep it server-side.
8. **Anthropic org settings**: request ZDR; use a dedicated Anthropic organisation/workspace for this product (ZDR and retention are per organisation; HIPAA readiness cannot be undone but is not needed); do not use Message Batches or Files API for student data; keep Covered Models off in this workspace.
9. **Logging hygiene**: never log prompts, notes or tool outputs; add a test that greps logs in the AI tests.
10. **Browser**: clear `st-chat` on logout and on `pagehide` for shared-device mode; offer "Clear chat" (exists) and store only rehydrated text for the current tab. Consider not persisting chat across reloads by default.
11. **Prompt injection stays covered**: `clean()` and tag defanging remain; tokens do not weaken them.

Expected effect: the provider sees no student names (except those the teacher types outside the roster), no IEP-like free text by default, and per-student numbers that are not individually identifying without the map. Effort estimate 3 to 5 days including tests (`tests/test_ai_*.py` already fake the client, so assertions on the outgoing prompt are straightforward).

## Parent-communication safeguards

- Drafts only: the server never sends mail and there is no parent contact field. Keep it that way; put sending behind an explicit teacher action and never batch-send.
- Visible "AI draft, review before sending" label on every draft, and the `source: ai|template` field already returned should be shown to the teacher.
- Prompt rules already prohibit speculation about home life, diagnoses or disability and mentions of other students; add output checks: reject drafts containing any other roster student's name or token, any email address or phone number, or words from a short blocklist (diagnosis, medication, custody, abuse, suicide, self-harm, behaviour-plan terms).
- If notes contain safety-sensitive terms, show "This note looks sensitive; follow your school's procedure, not this draft" and do not generate.
- Keep the deterministic template fallback when the AI is unavailable (exists).
- Log (not the text) that a draft was generated: user, student id, timestamp, tone, source, for the teacher's own audit trail.
- Use neutral greetings ("Hello,") and no teacher signature (exists), so no impersonation by the model.

## Deletion, export and retention (proposed capabilities)

1. `DELETE /api/students/{id}` already exists; add delete for note, section, course, and "delete my account and all my data" (two-step confirm).
2. `GET /api/export` (JSON, per teacher) and per-student export (JSON + CSV), covering what the school asks for under FERPA access requests.
3. Retention: default to purge accounts inactive 12 months; teacher-initiated "end of school year archive/delete" per course.
4. Backups roll off within 30 days; publish that window. Cloud Logging retention for the `_Default` bucket is 30 days (default); keep it.
5. Breach response runbook: who is notified (schools, state regulators), timelines by state, evidence preserved. Cloud Audit logs, Secret Manager access logs reviewed.
6. Publish a privacy policy and sub-processor list: Google Cloud (hosting, database/backups), Anthropic (AI), identity provider from ADR 0002 (Google or Clerk), email provider only if added.

## Cost (monthly, estimates)

Engineering effort dominates; vendor cost is small. Anthropic ZDR has no public price (sales conversation, not a checkbox). Assumptions: no extra infrastructure beyond ADR 0001/0002.

| Item | 1 teacher | 10 teachers | 100 teachers |
|---|---|---|---|
| Pseudonymisation and notes controls (one-off 3 to 5 days) | $0 running | $0 | $0 |
| Anthropic API (not changed by this ADR; fewer tokens if notes are excluded) | about $1 to 3 | about $10 to 30 | about $100 to 300 (estimate: chat ~20 turns/day, cached roster) |
| Counsel review of privacy policy and DPA template | one-off; budget outside this repo | | |
| Cloud Logging, audit logs | $0 (free tier) | $0 | about $0 to 5 |

## Risks

- Teachers type identifying information in free text regardless of controls. Mitigate with UI caution, not promise.
- ZDR not granted, or models change to Covered Models (30 day retention then applies regardless). Keep retention statements in the privacy policy conditional ("up to 30 days at our AI provider").
- Pseudonymisation bugs: a token that is not replaced reaches the user as gibberish; a name that is not tokenised reaches the provider. Test both directions (golden prompts).
- Over-claiming compliance ("FERPA compliant") on the website. Say "designed to support" until counsel and a school DPA exist.
- COPPA/FERPA obligations attach to the school-vendor relationship; a solo teacher using this for 150 students without district approval carries risk. Document that approval is the school's responsibility.

## Decision needed from the owner

1. Approve the minimisation plan (tokens, notes off by default, scrubbed free text) before any real roster is entered?
2. Pursue Anthropic ZDR and a DPA now, or accept 30-day provider retention for the pilot and disclose it?
3. Who is the first user population: the owner's own classes only, other teachers at the owner's school (district approval needed), or the public?
4. Will you commission counsel review (privacy policy, terms, DPA, COPPA position) before launching to anyone beyond the owner?

## Recommendation

Implement **Option 2 (pseudonymise prompts, notes excluded by default)** before any real student data is entered by anyone other than the owner
and request **ZDR plus a DPA** from Anthropic in parallel. Add the missing deletion/export endpoints and the browser-clearing fix before onboarding
the second teacher (this lines up with ADR 0002). Publish a short privacy policy and sub-processor list; engage counsel before approaching a school or district. Until
then, describe the product as a teacher's personal tool, do not market it to under-13 classrooms, and keep the per-course "AI off" switch available.

## Migration and rollback plan

- Ship minimisation behind a setting `AI_PSEUDONYMIZE=true` (default true), with a test suite asserting that no roster name appears in the outgoing request body (fake client in `tests/ai_fakes.py` already captures calls). Rollback is flipping the setting, with the understanding that doing so re-exposes names.
- Existing cached insights containing names: bump a cache version so they regenerate, or null the `insights` table once (it is derived data).
- Add deletion/export endpoints with tests; no schema change for deletion, small additions for audit rows.
- Browser: ship `sessionStorage` clearing on logout; no data migration.

## Sources (read 2026-10-02)

- Anthropic, API and data retention, https://platform.claude.com/docs/en/manage-claude/api-and-data-retention
- Anthropic, commercial data retention, https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data
- Perkins Coie on the amended COPPA Rule compliance dates, https://perkinscoie.com/insights/blog/ftc-finally-publishes-amended-coppa-rule-compliance-deadlines-set
- Code at origin/main (bb23101): `superteacher/ai.py`, `ai_tools.py`, `reports.py`, `routers/ai.py`, `routers/roster.py`, `web/src/components/Chat.jsx`, `web/src/scope.jsx`
- FERPA, COPPA and state-law summaries are from general knowledge; verify current text with counsel
