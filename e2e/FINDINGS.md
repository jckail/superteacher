# E2E / accessibility findings

Originally found by the Playwright + axe-core suite in `e2e/` against the JSX app. The merged app now uses TypeScript; historical source references below explain the original findings. Native fixes are identified explicitly; the old audit totals are not a fresh audit of the merged release.

## Resolved in the native app

### 1. Modal opener focus restoration

`web/src/components/ui.tsx` captures the opener during render, before a descendant's `autoFocus`, and restores it when the dialog unmounts. The same focus handling covers confirmation alertdialogs. Both opener-restoration cases in `specs/keyboard.spec.ts` passed in PR #15 CI run `36967196648`; that run reported them as failures solely because their old expected-failure annotations remained. Those annotations are now removed, retaining every focus assertion as regression coverage. The original JSX implementation captured the opener inside an effect after focus had moved.

### 3. School-day defaults and academic cutoffs

The old browser UTC/server-local mismatch is addressed by the configured IANA school timezone and authenticated `/api/calendar`. The TypeScript attendance and assignment forms consume the server's school day, and backend metrics use the same school calendar. See `docs/SCHOOL_CALENDAR.md`. The isolated E2E harness pins `SCHOOL_TIMEZONE=UTC` for deterministic school-day defaults; it does not determine the production school's timezone.

## Open or mitigated findings

### 2. Removing a student logs two 404s in the console and briefly refetches a deleted record
- Page: `/students/:id` -> "Remove student" -> confirm.
- Where: `web/src/pages/Student.jsx:69` (`onSuccess: () => { qc.invalidateQueries(); ...; nav('/roster'); }`).
- Cause: `invalidateQueries()` refetches the still-mounted `['student', id]` and `['insight', id]` queries before the route changes; both 404.
- Patch:
  ```diff
  - onSuccess: () => { qc.invalidateQueries(); toast.success('Student removed'); nav('/roster'); },
  + onSuccess: () => {
  +   qc.removeQueries({ queryKey: ['student', id] });
  +   qc.removeQueries({ queryKey: ['insight', id] });
  +   qc.invalidateQueries();
  +   toast.success('Student removed'); nav('/roster');
  + },
  ```
  Then delete `allowConsole(/status of 404/)` from `specs/student.spec.ts`.

### 4. `heading-order` (moderate, best-practice): empty states skip from h1 to h3
- Pages: `/roster`, `/gradebook`, `/attendance` when a section has no students (axe label `empty:*`; 3 pages x 4 viewport/theme combinations = 12).
- Selector: `.card.empty > h3`; `web/src/components/ui.jsx:68` (`<h3>{title}</h3>`).
- Patch: `<h2>{title}</h2>` (CSS `.empty h3` selector at `styles.css` then needs `.empty h2`/`h3`).
- Not blocking (impact is moderate).

### 5. Scrollable chart region is not keyboard-focusable (axe `scrollable-region-focusable`, serious) - mitigated in CSS
- Page: `/reports` at 390px (light + dark). Selector: `.table-wrap` wrapping the attendance SVG, `web/src/pages/Reports.jsx:48-49` (`style={{ minWidth: W }}` is wider than a phone).
- CSS mitigation shipped: at <=800px the chart scales down instead of scrolling (`.rep-chart[style]{min-width:0!important}`).
- Proper fix if horizontal scroll is wanted: `<div className="table-wrap" tabIndex={0} role="region" aria-label="Daily attendance chart">` and drop the inline `minWidth`, then remove the CSS override.

## Fixed in CSS (this PR, `web/src/styles.css`)
- **Mobile: Sign out and theme toggle were unreachable** below 800px (`.sidebar .side-extra { display:none }`). They now sit in a compact second row of the bottom bar; `.main` bottom padding and the toast offset were increased to clear it. Covered by `seeded/mobile.spec.ts` (theme toggle + Sign out visible at 390px).
- **Mobile: Attendance page scrolled horizontally** (page 450px wide in a 390px viewport; four status buttons per row). `.att-btns` now wraps at <=800px.
- Chart scroller a11y violation (see 5).

## Audit baseline (axe-core 4.x, tags wcag2a/2aa/21a/21aa/22aa + best-practice)
Before CSS fixes: 2 serious (`scrollable-region-focusable`, reports page, mobile light+dark), 12 moderate (`heading-order`, empty states). Zero `color-contrast` violations in light or dark theme on any audited page/state.
After: 0 serious/critical; the same 12 moderate `heading-order` items remain (need the JSX change in 4).


## Merged-release assertion updates

PR #15 CI run `36967196648` exposed two stale selectors alongside the fixed-focus annotations: `Quiz 1` also matched the new `Edit Quiz 1` button, and the insight test expected an environment-variable instruction removed from the teacher-facing UI. The gradebook header now uses an exact accessible-name match, while score persistence and server-value assertions remain intact. The insight case checks the current recorded-grades/attendance explanation, Rule-based label and nonempty headline. Note creation/reload and confirmation/cancellation/deletion assertions are unchanged. The updated cases require a fresh CI result; this edit does not claim they have rerun successfully.
