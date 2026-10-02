# E2E / accessibility findings

Found by the Playwright + axe-core suite in `e2e/`. File:line refs are against `web/src` on `origin/main` (JSX).
`web/src/**/*.jsx|js` was deliberately **not edited** (a TypeScript conversion is in flight elsewhere); the patches below are for whoever owns that work.
Items marked **fixed in CSS** were fixed in `web/src/styles.css` in this PR.

## Open (JSX / markup)

### 1. Modal does not return focus to the opener (a11y, WCAG 2.4.3) - serious UX
- Pages: every `Modal` with an `autoFocus` child (Add student, Add course, New assignment, Import CSV) and the confirm `alertdialog`.
- Rule: no axe rule (behavioural); caught by `specs/keyboard.spec.ts` (marked `test.fail`, so it turns red "unexpectedly passed" once fixed - then drop `test.fail`).
- Where: `web/src/components/ui.jsx:26` and `:41`.
- Cause: `opener = document.activeElement` is read inside `useEffect`, but a child's React `autoFocus` has already moved focus into the dialog during commit, so on close focus is "restored" to an element inside the dead dialog and lands on `<body>`.
- Patch:
  ```diff
  - const closeRef = useRef(onClose);
  + const closeRef = useRef(onClose);
  + const openerRef = useRef(document.activeElement);   // render phase: runs before children's autoFocus commits
  ...
  -    const opener = document.activeElement;
       const el = box.current;
  ...
  -    return () => { document.removeEventListener('keydown', onKey, true); if (opener?.isConnected) opener.focus?.(); };
  +    return () => { document.removeEventListener('keydown', onKey, true); const o = openerRef.current; if (o?.isConnected) o.focus?.(); };
  ```
  (Under StrictMode the ref initialiser can run twice; both reads happen before commit, so the value is still the opener.)

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

### 3. "Today" is the UTC date in the browser but the server's local date on the backend
- Pages: Attendance (default date and `max`), Gradebook (new-assignment due date), also `components/charts.jsx:82`.
- Where: `web/src/pages/Attendance.jsx:11`, `web/src/pages/Gradebook.jsx:10`: `new Date().toISOString().slice(0, 10)`; backend uses `date.today()` (`superteacher/metrics.py`, `reports.py`).
- Impact: a teacher in a US time zone after ~16:00-20:00 local gets *tomorrow's* date as "today": attendance sheet for tomorrow, new assignments due tomorrow, which the metrics engine treats as not yet due, so the class average shows "-". Reproduced in this suite when the server ran in PDT (the e2e server now pins `TZ=UTC`, as Cloud Run does, to stay deterministic).
- Patch: one shared helper, `export const today = () => new Date().toLocaleDateString('en-CA');` (local date, `YYYY-MM-DD`) and import it in both pages and `charts.jsx`. Better long-term: have the server expose its "today" (and school time zone) in `/api/overview`.

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
