# Read-side performance

AI tools previously hydrated every student, score, assessment and attendance record before applying a name or section filter. The optimized tool path filters student metadata in SQL, reads history as plain columns in batches of at most 200 students, and releases each batch after computing the shared metrics.

- `get_student` reads one student's history, or at most ten ambiguity candidates, and at most five notes. One unique hit uses four SQL statements regardless of roster size.
- `find_students` retains at most 25 ranked results, counts every matching student, and preserves stable name/id ordering, ties, unknown values last, and ascending/descending behavior. Name and section filters apply before reading history. SQLite tool matching uses a connection-local Python lowercase function to preserve Unicode substring behavior; `%`, `_` and backslashes are literal search characters.
- `class_stats` streams exact means, counts and section totals. It scans all relevant history because weighted averages, deterministic recent-three trends and risk depend on that history. It uses one roster query plus two history queries per batch. This trades additional bounded queries for substantially smaller peak memory.
- `iter_summaries(..., retain_scores=False)` preserves every aggregate metric while discarding detailed score lists once computed. `load_summaries` keeps its list return type and score detail for existing gradebook callers. Consumers that request a full list with score detail still retain those output values.

Memory is bounded by one batch's history plus retained output, rather than the whole roster's history. It is not independent of history length: an unusually large individual student's history still requires processing and retaining that student's score points during metric computation. No schema or index migration is required.

Metrics retain category weights, missing-score policy, same-day ordering and risk thresholds. A factual correction excludes attendance after the metric's as-of date, in both ORM and column paths. NULL scores for future assignments display `NOT YET DUE`; they do not count as missing. A missing assignment is an explicit NULL score row already due, consistent with roster synchronization and assessment creation.

## Reproduce

Run from the repository root with the project dependencies installed:

```sh
python -m tests.test_query_scale
python -m pytest tests/test_query_scale.py tests/test_ai_tools_scale.py
```

The manual benchmark creates a separate in-memory SQLite database containing only deterministic synthetic records: 1,000 students across four sections, 40,000 scores and 60,000 attendance rows. Dataset creation is outside the timed region. Each operation uses a fresh ORM session and garbage collection before measurement. `tracemalloc` measures Python allocations during the operation; timings include its overhead. No student database or model provider is contacted.

Observed on Python 3.12 in this workspace, 2026-10-01:

| Operation | Eager access seconds | Scoped/batched seconds | Eager peak MiB | Scoped/batched peak MiB | SQL before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Get one student | 4.931 | 0.028 | 113.23 | 0.28 | 7 → 4 |
| Find 25 by average in one section | 4.098 | 0.427 | 113.01 | 3.92 | 6 → 5 |
| Whole-class statistics | 4.984 | 2.061 | 113.01 | 4.11 | 6 → 11 |

The baseline reproduces the previous eager ORM read path and calls the public tool helpers; both sides use the current shared metrics and rendering. This isolates the actual database materialization cost. Every before/after returned result is asserted equal. These are representative local measurements, not production latency guarantees or database-server memory measurements.

Regression tests compare column metrics against ORM metrics, compare bounded ranking against an independent full-sort oracle, verify metric equality at historical cutoffs, assert scoped history parameter sets and query counts, verify no history ORM hydration, and cap note and ambiguity reads. They assert data boundaries and deterministic results rather than brittle wall-clock thresholds.
