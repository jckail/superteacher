# Section transfers and grade history

Changing a student's section preserves all existing `Score` rows, including recorded zeroes and explicit ungraded rows. The existing assessment relationship identifies each score's section; no new table or migration is needed. Transfer synchronization inserts a NULL score only for an assessment in the destination section that has no existing score for this student. It never deletes or overwrites an existing score.

Current student details, roster summaries, gradebooks, reports and AI tools compute grades, missing assignments, homework completion and grade trends from assessments in the student's **current section**. The ORM metric path compares assessment and student section IDs; the column summary path enforces the same condition in SQL. Unflushed ORM fixtures with both IDs unset retain their previous metric behavior. Prior-section grades cannot change current averages, trends, missing counts or grade-based risk signals.

Attendance and notes remain attached to the student throughout a move. Attendance is not partitioned by section in the existing data model; it remains part of the student's attendance metrics, limited by the metric's as-of date. Returning to a prior section restores its raw score rows as active grades. Assignments added to that section while the student was away receive new ungraded rows on return.

## History API

`GET /api/students/{student_id}/grade-history` returns:

```json
{
  "student_id": "student-id",
  "active_section_id": "current-section-id",
  "sections": [
    {
      "section_id": "prior-section-id",
      "section": "Period 1",
      "course_id": "prior-course-id",
      "course": "Algebra",
      "scores": [
        {
          "assessment_id": "assessment-id",
          "title": "Quiz 1",
          "kind": "quiz",
          "due_date": "2026-09-15",
          "max_points": 100.0,
          "points": 0.0,
          "pct": 0.0
        }
      ]
    }
  ]
}
```

Only sections with preserved scores outside the active section appear. Ungraded rows have `points: null` and `pct: null`; recorded zeroes remain numeric zeroes. An existing student with no prior-section rows receives `sections: []`. An unknown student receives 404.

Groups are ordered by course name, section name and section ID. Scores are ordered by due date, title and assessment ID. The endpoint performs one student-metadata query and one student-scoped column query, without hydrating other students or ORM score histories. It exposes raw records and section/course context, without presenting old section averages as current grades.

This is retained grade history, not an immutable transcript. Existing assessment titles, kinds, due dates and maximum points remain editable, and history displays their current values. The model stores no transfer timestamps, enrollment intervals or historic assessment snapshots. Deleting an assessment still deletes its score rows under the existing explicit cascade policy. Moving alone preserves them.

## Verification

```sh
python -m pytest tests/test_student_transfer.py tests/test_transfer_metrics.py tests/test_backend_audit.py
```

Regression cases cover recorded zero and nonzero grades, cross-course transfers, destination missing rows, unchanged old score IDs and raw points, moving back, notes and attendance retention, active ORM/column metric equivalence, unflushed fixtures, unknown-student behavior, student-scoped history reads and existing score-write restrictions for students outside a section.
