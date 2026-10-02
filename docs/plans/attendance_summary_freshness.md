# Attendance settlement refreshes the deterministic class report

Attendance saves reconcile attendance, overview and student queries, but the
`['report-summary', sectionId]` cache currently remains fresh. A teacher who
opens Reports after saving attendance can therefore see the previous attendance
rate until cache expiry or another explicit refresh. Same-day cached summaries
isolate this gap from Reports' existing school-day rollover behavior.

Bounded scope: invalidate exactly the submitted section's deterministic report
summary from Attendance's existing mutation `onSettled`, using captured mutation
variables and the original hook QueryClient. Preserve existing optimistic marks,
conditional rollback, mutation serialization, and reconciliation. This applies
after successful and failed saves because a failed response can leave server
commit status uncertain. Other sections and descendant report keys stay fresh.

Student Insight remains a separate freshness gap: its GET can generate paid AI
content. This change does not invalidate Insight, alter provider policy, or
trigger parent-update generation. Existing Insight caching and manual parent
generation remain unchanged; that broader policy requires a separate decision.

## RED → fix → GREEN → independent review

1. Add `web/src/test/AttendanceSummaryFreshness.test.tsx` before production edits.
   Mount actual Attendance and Reports with a real QueryClient, fresh same-day
   cached summaries, mocked transport, and deferred attendance PUTs. Verify the
   no-write control, late A settlement under A/B/ABA scope transitions, report
   navigation with updated values, unrelated section/descendant cache freshness,
   failure rollback, serialized later writes, bulk marking, and actual Root
   session replacement. No provider calls or parent generation are authorized.
2. Parent verification owner runs the focused file and records RED attributable
   to report freshness. Production edits wait for that explicit result. No
   dependency install, browser, cloud action, or parallel broad verification.
3. Add one exact report-summary invalidation using `variables.sectionId` in
   existing Attendance settlement, alongside existing reconciliation. Do not
   replace the mutation lifecycle or use the current visible section.
4. Parent reruns the focused file for GREEN, then existing relevant attendance,
   report, and auth checks plus frontend typecheck/lint as appropriate. Use the
   shared heavy-check gate for expensive checks and inspect running jobs first.
5. Independent review verifies source, assertions, captured section/client
   ownership and scope exclusions. Parent owns Git operations and consolidated
   Graphify/Codemogger refreshes after settled edits. Record actual outcomes;
   commands below are recommendations, not claims of execution.

Focused command from this worktree's `web` directory:

```sh
/home/jkail/.local/bin/agent-heavy-check -- npm test -- src/test/AttendanceSummaryFreshness.test.tsx
```

Discovery: shared Graphify returned unrelated corpus paths rather than native
Superteacher source. This exact sibling checkout has no Codemogger index, so live
scoped source was inspected. The dated canonical `docs/agent-architecture.md`
orientation was read because that file is absent from this base worktree.

Verification checkpoint, 2026-10-02: the parent ran the focused file before
production changes (native handle 5679, exit 1, 7.698 seconds). The eight cases
produced one passing no-write control and seven genuine failures: submitted
report-summary caches stayed fresh, Reports retained prior attendance, or the
original session client lacked the summary invalidation. With that explicit RED
authorization, Attendance gained the single exact invalidation above.

The parent then recorded GREEN (native handle 65305, exit 0, 7.54 seconds):
60 tests passed across this eight-case regression file, `Operations`,
`ReportsCalendar`, and `ParentDraftSettlement`. Frontend typecheck, focused
ESLint, and diff checks also passed. Independent task and complete-change reviews
both approved SPEC and QUALITY with no blocking findings. These are parent-reported checks; the implementation
agent ran no tests, builds, installs, indexes, or Git mutations.
