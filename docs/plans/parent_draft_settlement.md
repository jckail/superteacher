# Parent draft regeneration settlement

Status: root RED reproduced the pending-edit loss (one control passed, one regression failed in 2.36 seconds); root approved the retained-alternative policy and authorized scoped production work. Following the keyboard-focus review fix, final root GREEN passed 71 tests in five files in 8.26 seconds; types, focused ESLint and diff check passed (root verification process 24660 exited0). Production and 31 cases are frozen pending independent review and root commit. Base: `68f2fa2`; isolated checkout: `/home/jkail/projects/superteacher-parent-draft-settlement-20261002`. Root owns verification, Git and external execution. This records local focused checks only, not new full CI, browser/provider runtime, build or deployment verification.

## Problem and verified source

In actual `web/src/pages/Reports.tsx`, an existing parent draft remains editable while Regenerate awaits its POST. Subject and Message call `edit()`, which advances clipboard-related `draftRevision` through `clearCopied()`. The generation `current()` guard checks mounted state, student/tone/reset lifecycle revision and request sequence, but not text edits. Success unconditionally installs the returned draft for the same lifecycle. Thus late generation can replace both teacher fields and their existing source. This is source-reachable through enabled controls; root must execute the regression before any runtime defect claim.

Scope selection/tone/reset, section key remount, generation latch and clipboard completion already have independent guards. Summary/day refresh remains separate from explicit generation. Preserve these contracts. ParentUpdateOut currently contains only subject/body/source; artifact dates and backend provenance are outside this change.

## Proposed behavior for root ruling

Keep Subject and Message editable while generation is pending. Capture a monotonic **text-edit revision**, separate from clipboard resets, at generation start together with existing request/lifecycle ownership. Any intervening text edit counts, including away-and-back to identical text. If the lifecycle is current and text is unchanged, install the response as today. If text changed, retain both current raw fields and current source, and store the full response as one temporary alternative owned by that same composer/student/tone lifecycle.

Show `A new draft is ready. Your edits were kept.` with `Review new draft` and `Discard new draft`. Review reveals the actual alternative subject/message and AI/template source without modifying current fields. Only the review then exposes `Replace my edited draft`, explicitly explaining that both current fields will be replaced. That action installs the alternative fields/source together, clears clipboard state and consumes the alternative. Closing review keeps the alternative available; discard removes it without touching current fields. Further teacher edits never apply the alternative automatically. Copy and Open in email continue using the current edited fields until explicit replacement.

Keep only one alternative in local state. An explicit subsequent Generate/Regenerate starts a new request and clears the older alternative/review; no automatic second request or retry. Existing identity/tone/reset/invalid-roster/section/unmount/session boundaries discard the alternative and reject late completion. Ordinary generation failure retains current draft/raw edits and visible request error; optionally add `Generation failed. Your draft and edits were kept.` when a draft exists, without weakening typed-404 reset behavior. Initial generation with no editable draft follows existing success behavior. No backend/API/source metadata additions or provider work are needed.

Root approved policy following RED: retain the alternative with explicit review/replace/discard, preserve current copy feedback/revision when the alternative arrives, keep existing current() lifecycle guard and failure/manual-retry behavior, count away/back edits, and carry each artifact's existing source with it. The separate text-edit revision avoids treating copying as a text edit or gratuitously resetting current clipboard feedback on alternative arrival.

## Global constraints

- First phase owns only this plan, `web/src/test/ParentDraftSettlement.test.tsx`, and ignored task reporting. No production edit until root executes RED and approves policy.
- Future source ownership, if authorized, is ParentComposer settlement/edit/alternative UI in `web/src/pages/Reports.tsx` only. Preserve global generation latch, existing identity/tone/section/session/copy guards, report-summary calendar/read policy, roster pagination, source DTO and endpoint contract.
- Actual controls remain editable; do not introduce a pending edit lock or use inert/modal background interactions to manufacture a race.
- Preserve both raw fields verbatim, including whitespace/newlines, on conflicting success/failure. Source belongs to the current draft until replacement of the complete generated alternative.
- Exactly one POST per explicit request; no automatic generation/provider calls, retry spend, new backend provenance or model-evaluation scope.
- Root is sole test/build/CI/Git/cloud/Graphify-refresh owner. No browser needed. Reuse root-created dependency symlink; do not stage/delete it.

## Frozen initial RED

`ParentDraftSettlement.test.tsx` has two mounted actual Reports cases using actual ScopeProvider/picker, roster query and calendar/summary reads with exact API dispatch. First generate returns an existing template draft; Regenerate uses a genuinely deferred POST, captured student/tone/section path/body, enabled Subject/Message and pending-disabled button. Completion is awaited via generation latch settlement.

1. Unchanged control: response replaces both fields/source together and email uses the response; summary cache is unchanged.
2. Pending teacher edits: change both enabled fields to raw padded text/newlines, resolve the real deferred POST, require same DOM fields with exact raw edits, original template source and email using edited text; exactly two explicit requests total and unchanged summary cache. Current source is expected to fail field retention. This test does not require proposed alternative UI before policy approval.

## Authorized implementation sequence, pending root ruling

1. Root runs frozen RED and records actual control/regression results. Root rules on the retained-alternative policy above before source implementation.
2. If approved, implement local text-edit revision and bounded alternative/review actions in ParentComposer, retaining existing ownership guards. No generic settlement framework or unrelated source edits.
3. Expand mounted cases for subject-only/message-only/away-back edits, unchanged or changed failure/retry, review/close/discard/explicit replacement, subsequent edits after review, copy/email/current source, stale clipboard completion, and alternative disposal on actual student/tone ABA, section remount, selection reset and Root expiry/logout/relogin. Verify calendar summary refresh does not generate or consume an alternative. Reuse existing ReportsCalendar/ReportPicker coverage where it directly proves retained contracts.
4. Root owns focused GREEN, type/lint and required checks, review, Git integration and refresh. Record only actually verified evidence; no new deployed/full-CI/runtime claims from source/test preparation.

## Context coverage and limitations

Read parent AGENTS orientation, live checkout Reports/Scope/roster/types and existing ReportsCalendar/ReportPicker fixtures; architecture map is an untracked parent file absent from this isolated base, so it supplied navigation only and live source supplied contracts. Shared Graphify CLI queried first for native Superteacher ParentComposer; it returned unrelated corpus/private-evidence paths, no applicable source. Those unrelated paths were not investigated. Root verified this exact checkout has no Codemogger index; prior indexing exited75. Dependency-free CLI text discovery is available; Codemogger/LSP MCP is not exposed in this session. No index/install retry or complete-index coverage claim. Agent Hub context for this exact checkout returned the repository-selection warning; root owns project checkpointing. No checks executed by producer.

## Published combined acceptance checkpoint

Root committed isolated47f5b4f and integrated890658e; complete task/full-branch reviews pass SPEC/QUALITY with no remaining findings. Combined source11249217 is pushed to main/workingbranch and exact CI37043235047 passed all seven jobs:1399API/342web/4browser/84E2E/259lockedDocker. Root combined40tests/3files8.31s/types also passed. Its immutable bundle/source/context passed independent review and root validation; protectedbuild56016 exited75 before helper started (no intent/proof/image/cloud mutation). Separate runtime acceptance remains pending. Current canonical source index completed201files/1744chunks with verified live hashes; this isolated checkout is not indexed. See DEPLOYMENT_STATUS.md for the current authoritative release/remaining gates.
