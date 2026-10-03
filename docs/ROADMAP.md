# Roadmap and ideas

The product's loop is **see who needs help → understand why → act → learn whether it worked**. Today Super Teacher is strong on the
first two. The ideas below are organised by where they extend that loop. Committed follow-ups (launch, reliability, trust) live in
the GitHub issues and the Linear project **Super Teacher**; this file is the brainstorm behind the "ideas" backlog.

Effort: **S** days, **M** about two weeks, **L** a month or more. Everything assumes the demo rule: synthetic data only, until the
privacy work (ADR 0003, issues "AI data minimisation" and "Terms and privacy notice") is done.

## Top bets (what to do first, and why)

| # | Bet | Why now | Effort | Depends on |
|---|---|---|---|---|
| 1 | **"Try it now" sandbox** | Sign-in email is currently the single point of failure for launch. An anonymous, ephemeral, rate-limited sandbox (own synthetic classroom, resets daily, no email) turns the public demo into a one-click experience and keeps email as an upgrade for people who want to keep their data. | M | accounts, quotas |
| 2 | **Morning brief** | The core promise delivered without opening the app: a short digest of the 3 to 5 students who need attention, with the reason and one suggested action, by email or a share link. Reuses the mailer and the risk engine. | M | working email |
| 3 | **Intervention log with outcomes** | Closes the loop. Record what was tried ("small-group reteach", "called home"), then show whether the student's trend moved. Becomes the dataset for everything smart later. | M | none |
| 4 | **Citations in AI answers** | Every number or name in a chat answer links to the record it came from. Builds trust, and is the cheapest defence against wrong answers. | M | eval harness |
| 5 | **Parent update, batch and translated** | Drafts for a whole at-risk list at once, strengths-first, in the family's language, edited by the teacher, sent through the mailer on approval. | M | privacy notice |
| 6 | **Grading policy** | Teachers will not trust numbers that differ from their official gradebook (ADR 0004). | M | none |
| 7 | **Item analysis** | Which assignment or question did most of the class miss? Turns the gradebook into a reteach planner. | S | none |
| 8 | **Infrastructure as code + CI deploys** | The portfolio repo already deploys through GitHub Actions with Workload Identity Federation and a canary. Doing the same here removes laptop deploys and the hand-built bucket/alerts. | M | none |

## Close the loop: from insight to action
- **Intervention plans** (tracked): reviewable actions linked to evidence, confirmed by the teacher before anything is saved.
- **Small-group builder** (implemented in source, [PR86](https://github.com/jckail/superteacher/pull/86); deployment acceptance pending): Gradebook groups students by due unscored work or weak assignment type, shows recorded evidence and suggests consecutive slots using teacher-chosen availability. Unscored work is not proof of non-submission; suggestions stay local to the page. See the [teacher workflow](teacher-workspace.mdx#small-group-suggestions). The feature remains open within [JCK-80](https://linear.app/jckail/issue/JCK-80/idea-small-group-builder-and-conference-sheet) until release acceptance; source integration does not establish deployment.
- **Conference sheet** (implemented in source, [PR84](https://github.com/jckail/superteacher/pull/84)): Roster links to a one-page student summary with trend, attendance, due unscored work and explicitly selected notes. Current-school-day and fit checks guard printing; account dialogs and assistant transcripts stay out of print. See the [teacher workflow](teacher-workspace.mdx#conference-sheets). Deployment acceptance is separate: consult the [operator runbook](OPERATOR_RUNBOOK.md) and [status ledger](DEPLOYMENT_STATUS.md), then confirm actual runtime readback. This completes the conference-sheet portion of JCK-80, not the small-group builder.
- **Assistant that can write, with confirmation**: create an assignment, mark attendance, add a note. Every write shows a diff and needs a click. M.
- **Nudges, not noise**: "three absences this month", "average dropped 12 points in two weeks", delivered once, dismissible, with the evidence.

## Data in
- **Roster/gradebook import wizard**: column mapping, preview, undo; then Google Classroom, Canvas and OneRoster/Clever connectors. L.
- **Photo of a paper gradebook → scores** using a vision model, always with a review screen. M.
- **Fast entry**: paste a column from a spreadsheet, keyboard-only grid (partly there), mobile quick attendance, seat map. S to M.
- **Standards-based grading and rubrics**: map assignments to standards and report mastery, not just percentages. L.

## Insight quality
- **Item analysis and assignment difficulty** (bet 7).
- **Cohort and class comparisons**, trend overlays, attendance patterns by weekday and tardiness streaks. S to M.
- **Explainable early-warning score** with backtesting against history. Keep it transparent: the reason is always shown, never a black box. L.
- **Equity lens** (optional, off by default): surface disparities across groups the teacher defines. Privacy-sensitive; needs counsel first.

## AI assistant
- **Lesson-plan, quiz and differentiated-assignment generator** aimed at the weak topics the data shows. M.
- **Eval harness** (tracked) with a golden classroom and a scorer; add it to CI as a spend-capped nightly.
- **Model routing and cost control**: small model for insights, larger for chat, prompt caching tuned, batch API for nightly work, a daily spend dashboard. S.
- **Voice notes**: dictate a note, get a cleaned-up summary (browser speech API first). S.
- **Per-teacher preferences** (tone, grading philosophy, reading level of parent letters). S.

## Platform and product
- **Schools and co-teachers**: organisations, shared classes, roles. Needs tenancy v2 and Postgres. L.
- **Passkeys (WebAuthn)** alongside email links: faster, phishing-resistant, no email dependency. M.
- **PWA and offline entry** with sync, push notifications for the morning brief. M.
- **Spanish and other languages** for the UI and parent drafts. M.
- **Exports**: CSV/XLSX/Google Sheets, calendar feed for due dates. S.
- **Student/parent read-only portal**: high value, high privacy cost; only after real accounts and counsel review. L.

## Engineering upgrades
- **Terraform for the Cloud Run service, bucket, secrets, alerts and domain mapping**, plus GitHub Actions deploys with Workload Identity Federation (no laptop deploys, no hand-set env vars). M.
- **Canary traffic splits** and automatic rollback on error-rate or failed restore. S to M.
- **Postgres path** (Cloud SQL) when a trigger fires: more than one writer, RPO needs, or about 10 active teachers (ADR 0001). L.
- **Error tracking and a real dashboard** (latency, error rate, AI spend, replication lag) on top of the new metrics. S.
- **Performance budgets** enforced in CI (tracked).
- **Server-Sent Events instead of WebSockets** for chat if proxies or mobile networks become a problem. S.

## Explicitly not now
Real student data, a student-facing app, anything that sends email to parents without a teacher's click, and any "predictive" label
that cannot show its reasons.
