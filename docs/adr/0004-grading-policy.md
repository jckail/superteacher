# ADR 0004: Configurable grading policy

- Status: Proposed, needs owner decision
- Date: 2026-10-02
- Deciders: Jordan Kail (owner)
- Related: ADR 0002 (policy owner = teacher, later school), ADR 0001 (new tables)

## Context

The original proposal referenced commit `bb23101`. The current source audit at
`4f7ba66` still finds fixed grading rules in `superteacher/metrics.py`:

- Category weights `KIND_WEIGHTS`: test 40%, quiz 20%, homework 25%, project 15%, **renormalised over categories that have at least one graded score**. Category score is points earned over points possible within the category (a total-points average inside each category).
- Letter thresholds `_LETTERS`: 93 A, 90 A-, 87 B+, 83 B, 80 B-, 77 C+, 73 C, 70 C-, 60 D, else F, with a 4.0 GPA mapping (D has no plus/minus, there is no D+ or D-).
- Missing work: a score with `points = NULL` is excluded from the average (it does not count as zero) and is counted in `missing` and in the homework-completion rate (completed over homework due). Only assessments with `due_date <= today` count.
- Extra credit: finite nonnegative scores above a positive maximum are supported,
  preserved and counted without a 100% clamp. Percentage overflow is rejected
  before writes. Zero-max bonus assessments remain invalid; numerator-only bonus
  policy is a proposed future capability.
- Attendance: excused days are removed from the denominator; present and tardy count as attended; absent counts against. `attendance_rate = attended / (all - excused)`.
- Grading periods: none. The average is cumulative over every assessment to date.
- Risk flags (`_assess_risk`): below 65 average = 3 points, below 72 = 2, trend drop, attendance under 80 or 90, homework completion under 70; at-risk at 3 or more points, watch at 2.
- Every consumer (roster, gradebook, overview, reports, CSV, AI context) calls the same `metrics` functions, which is a strength: **one policy object can change all of them consistently**. Conversely, the AI and the parent drafts quote these numbers, so a policy change changes what is told to parents.

Teachers' real policies differ: many use homework-light weights, a plain 90/80/70/60 scale, "missing counts as zero" or "minimum 50%", drop-the-lowest-quiz, extra credit, and quarterly or semester terms. Without configurability, the app computes a number the teacher's official gradebook does not, which erodes trust faster than any other defect.

## What must be configurable

| # | Setting | Values | Level it is set at |
|---|---|---|---|
| 1 | Category weights | any categories (name, weight %), weights sum to 100; renormalise when a category is empty (on/off) | course default, section override |
| 2 | Category mapping | assessment kind (today an enum) to category; later free-form categories | course |
| 3 | Letter scale | list of (threshold, letter, GPA points); plus/minus on/off; rounding rule before lookup (none, nearest whole, half up) | global default (school), course override |
| 4 | Missing-work policy | `exclude` (today), `zero`, `floor` (replace with X%, e.g. 50), `exclude_until_days_late` N | course, section override |
| 5 | Extra credit | uncapped finite scores above a positive maximum (today); proposed numerator-only bonus assessments or configurable cap | course |
| 6 | Drop lowest | drop N lowest in category (quiz, homework), only if at least M scores | course category |
| 7 | Averaging method | `category_weighted` (today) or `total_points` | course |
| 8 | Attendance counting | excused counts as present or is excluded (today); tardy = attended (today), half-absence, or K tardies = 1 absence | global default, section override |
| 9 | Grading periods | none (cumulative, today) or terms (named, start/end), each assessment falls in a term by `due_date`; period grade, cumulative grade, and final = weighted mean of terms | course/section |
| 10 | Risk thresholds | failing line (65), watch line (72), attendance lines (80/90), homework line (70), trend triggers | global default, teacher override |
| 11 | "Today" rule | count only assessments due by today (today) or all graded | global |

### Levels and resolution

Three levels with first-match resolution: **section > course > teacher/school global > system default**. The system default is a built-in object whose values are
exactly today's constants, so with no stored policy every number in the app is unchanged. Terms (item 9) and attendance counting (item 8) attach naturally to the section/term; weights, scale and missing-work usually attach to the course (and sometimes a school mandates the scale; that is what the global level and, later, ADR 0002's organisation tier are for).

### Storage and compatibility

- New table `grading_policies(id, scope_type in {system, owner, course, section}, scope_id, name, version, json, created_at, updated_at)` with a JSON document validated by a Pydantic model (`GradingPolicy`) carrying a `schema_version`. `policy = resolve(section)` is computed once per request and passed into `metrics.compute*` (the pure functions gain a `policy` argument defaulting to `DEFAULT_POLICY`, so existing call sites and tests keep working).
- **No data rewrite**: scores and attendance rows stay as entered. A migration only creates the table. Existing deployments get no rows, hence default behaviour, hence identical numbers (tests assert numeric equality against the current outputs; the 82.2 B- example below is a golden case).
- Extra credit and drop-lowest need small additions: `assessments.is_extra_credit` (bool, default false) or `max_points = 0` accepted by validation; and `assessments.category` (nullable, falls back to `kind`). Both are additive migrations.
- Terms need `terms(id, scope_id, name, start_date, end_date)`; assessments are assigned by due date, so no per-assessment column.
- `metrics.fingerprint` must include the policy hash so cached AI insights are invalidated when the policy changes.
- Show the active policy on the gradebook ("Weighted: tests 40, quizzes 20...; missing excluded") and in CSV/report headers, and include it in AI context (one line), so the chat can explain a grade.
- Policy changes are retroactive by design (grades are derived) but should create an audit row (who, when, before/after JSON) because it changes what parents are told.
- Grade changes visible to parents: a policy edit must show a preview "this changes the grade of N students" before saving.

## Worked examples (same student, one option changed at a time)

Student "Sam", section data to date (all assessments are due; points shown as earned/possible):

| Category | Scores | Category average |
|---|---|---|
| Tests | T1 72/100, T2 84/100 | 156/200 = 78.0% |
| Quizzes | Q1 8/10, Q2 10/10, Q3 5/10 | 23/30 = 76.67% |
| Homework (5 assigned) | H1 10/10, H2 9/10, H3 missing, H4 8/10, H5 missing | graded 27/30 = 90.0%; 2 missing |
| Project | P1 88/100 | 88.0% |

Baseline policy = today's code: weights 40/20/25/15, missing excluded, scale 93/90/87/83/80/77/73/70/60.

`average = 0.40*78.0 + 0.20*76.67 + 0.25*90.0 + 0.15*88.0 = 31.20 + 15.33 + 22.50 + 13.20 = 82.23`, letter **B-** (80 to 82.99).

| Option changed (everything else baseline) | Calculation | Average | Letter | Change |
|---|---|---|---|---|
| Baseline (defaults) | as above | 82.23 | B- | |
| Homework-heavy weights 20 tests / 10 quiz / 50 homework / 20 project | 0.20*78 + 0.10*76.67 + 0.50*90 + 0.20*88 = 15.60 + 7.67 + 45.00 + 17.60 | 85.87 | B | +3.63, one letter up |
| Missing work counts as zero | homework = 27/50 = 54.0%; 0.4*78 + 0.2*76.67 + 0.25*54 + 0.15*88 = 31.20 + 15.33 + 13.50 + 13.20 | 73.23 | C | -9.00, **two letters down** |
| Missing work floored at 50% (each missing = 5/10) | homework = (27+10)/50 = 74.0%; 31.20 + 15.33 + 18.50 + 13.20 | 78.23 | C+ | -4.00 |
| Extra credit: +3 bonus points on quizzes (numerator only) | quizzes = 26/30 = 86.67%; 31.20 + 17.33 + 22.50 + 13.20 | 84.23 | B | +2.00 |
| Drop lowest quiz (Q3 5/10) | quizzes = 18/20 = 90.0%; 31.20 + 18.00 + 22.50 + 13.20 | 84.90 | B | +2.67 |
| Total-points method (no categories) | (156 + 23 + 27 + 88) / (200 + 30 + 30 + 100) = 294/360 | 81.67 | B- | -0.57 |
| Letter scale: plain 90/80/70/60, no plus/minus | 82.23 falls in 80 to 89.99 | 82.23 | B | same number, one step up |
| Letter scale: rounding to nearest whole first (82) with the default scale | 82 is still below 83 | 82 | B- | none (shows when it matters: 82.5 would round to 83 and become B) |

Why this matters: choosing "missing = zero" instead of "excluded" moves Sam from B- to C; choosing "excluded" while a school expects zero would make every missing-work conversation wrong.

### Attendance counting (20 school days: 15 present, 2 tardy, 2 absent, 1 excused)

| Rule | Calculation | Rate | Effect on risk flags (baseline average 82.2 adds 0; homework completion 3/5 = 60% adds 1; trend assumed neutral) |
|---|---|---|---|
| Baseline: excused excluded, tardy attended | (15+2) / (20-1) = 17/19 | 89.47% | under 90: +1, total 2 = **watch** |
| Excused counts as present | (15+2+1) / 20 | 90.00% | no attendance point, total 1 = **on track** |
| Tardy counts as half an absence | (15 + 2*0.5) / 19 = 16/19 | 84.21% | +1, total 2 = watch |
| 3 tardies equal 1 absence (2 tardies = 0.667 absence) | (19 - 2 - 0.667) / 19 | 85.96% | +1, total 2 = watch |

A one-tenth-of-a-point rule difference flips a student between "watch" and "on track", which is why the attendance rule must be explicit and shown.

### Grading periods

Terms: Term 1 contains T1, Q1, Q2, H1, H2, H3; Term 2 contains T2, Q3, H4, H5, P1 (weights renormalised over categories present).

| View | Calculation | Average | Letter |
|---|---|---|---|
| Term 1 only | tests 72, quizzes 18/20 = 90, homework 19/20 = 95; (0.40*72 + 0.20*90 + 0.25*95) / 0.85 = 70.55/0.85 | 83.00 | B |
| Term 2 only | tests 84, quizzes 5/10 = 50, homework 8/10 = 80, project 88; 0.40*84 + 0.20*50 + 0.25*80 + 0.15*88 | 76.80 | C+ |
| Cumulative (today's behaviour) | baseline above | 82.23 | B- |
| Final = mean of the two terms (equal term weights) | (83.00 + 76.80) / 2 | 79.90 | C+ |

The same student is a B, a C+, a B- or a C+ depending on whether the question is "this term", "so far", or "final". The UI must label which one it shows, and the AI context must say which period it is describing.

## Options

1. **Keep hard-coded rules and document them.** Zero work. Rejected: teachers' policies differ and trust suffers.
2. **A few global settings in env/config.** Cheap but wrong level (policies differ per course).
3. **Policy objects with section > course > owner > system resolution (recommended).** Moderate work, no data change, defaults preserve all current numbers.
4. **Per-assessment ad hoc overrides** (exclude one assignment, custom max) on top of 3. Useful later, skip now.

## Cost (monthly, estimates)

No infrastructure cost: a small table and some CPU. Engineering effort (estimates for one engineer): policy model and resolver 1 day; metrics refactor with golden tests 2 days; extra credit, drop-lowest, missing-work, attendance rules 2 days; terms 2 to 3 days; UI (policy editor, preview of impact, labels) 3 to 4 days; AI/report text updates and docs 1 day. Total about 10 to 13 days for everything; the first useful slice (weights, scale, missing-work policy, attendance rule at course level) is 4 to 5 days.

| Teachers | Monthly infra cost |
|---|---|
| 1 / 10 / 100 | about $0 (a few KB of JSON per course; negligible query cost) |

## Risks

- **Silent grade changes**: any default drift changes grades parents see. Mitigate with golden-value tests (the Sam example above becomes a test) and by making the system default literally the old constants.
- **Wrong mental model of "missing"**: `NULL` points currently means "not turned in"; adding `zero` or `floor` must not write rows, only change the computation.
- **Performance**: metrics are computed per student per request; policy lookups must be resolved once per request, not per student.
- **Complexity creep**: do not expose every knob at once. Ship templates ("Points-based", "Weighted categories", "Standards-style later").
- **Parents and AI consistency**: the chat and the draft emails quote the numbers; they must quote the same policy-aware numbers and name the period.
- **Legal/school policy**: some schools mandate scales and weights; admin-locked policies come with ADR 0002's organisation tier.

## Decision needed from the owner

1. Which controls are in the first release (recommended: weights, letter scale, missing-work policy, attendance rule), and which wait (terms, drop-lowest, extra credit, risk thresholds)?
2. Default for missing work in new courses: keep "exclude" (today) or change to "zero"? (Existing courses keep current behaviour regardless.)
3. Whose policy wins when a school sets one: teacher (default) or school (needs the organisation tier)?
4. Are grading terms needed before the first school year rollover (recommended: yes, within a quarter), given a cumulative-only average becomes misleading after the first term?

## Recommendation

Adopt **Option 3**. Implement `GradingPolicy` with system defaults equal to today's constants, store overrides at course (and section) level, ship first the four-control slice
(weights, letter scale, missing-work policy, attendance counting) with an impact preview and golden tests, then terms, then extra credit and drop-lowest. Show the active policy and the
period on every grade surface and in AI context. Keep global (owner-level) defaults so a teacher sets their scale once.

## Migration and rollback plan

- Inspect the actual Alembic head before implementation and choose a unique
  additive successor. `0003_accounts` is already landed; the old tentative
  `0003_grading_policies` name must not be reused. No default override rows or
  inferred terms/enrollment dates should be written for existing records.
- Feature flag `GRADING_POLICIES_ENABLED` hides the editor; the resolver returns the system default when disabled.
- Golden tests: current outputs for the seeded demo data (deterministic in `seed.py`) must be byte-identical with the flag on and no policies stored.
- Disabling the flag returns computation to defaults, which changes derived
  grades after real overrides exist. Schema tolerance is not semantic rollback
  safety. Define and test a compatible policy/audit restore before release;
  preserve overrides rather than casually dropping their table.

## Current follow-ups and unresolved requirements

This remains a proposal, not implemented configurability. Source `07974de`
implements truthful parent-template wording (there is no academic-term model) and
captured Gradebook `as_of` with forward school-day rollover revalidation. They
preserve current formulas, raw scores and student-wide attendance. Independent
reviews, exact CI and synthetic staging cutoff checks passed; artifact and recovery
evidence belongs in the release ledger. These fixes do not add grading policies,
terms, retrospective enrollment dates or an atomic database snapshot.

Before policy/term/enrollment work, specify scope resolution and policy versions,
zero/all-empty weights, missing-work treatment, rounding, retroactive versus
frozen reports, term overlaps/unassigned dates and attendance windows. Carry the
same policy/cutoff through ORM and bounded column reads, exports and AI/cache
fingerprints. Existing rows cannot reveal enrollment start/end dates or historical
section attribution: any prospective ledger must distinguish recorded time from
confirmed effective dates and preserve unknown historical provenance. Review
concurrent transfers, export/delete behavior and restore compatibility separately.

## Sources

- Repository at origin/main (bb23101): `superteacher/metrics.py`, `models.py`, `ai_tools.py`, `reports.py`. All numbers in the worked examples were recomputed by script on 2026-10-02 and are reproducible by hand from the tables above.
