"""Regression: class_summary used to scan every student's scores once per assessment (quadratic in assessments).

Measured before the fix (300 students): 20 assessments 39 ms, 60 -> 296 ms, 120 -> 774 ms, while the linear
gradebook CSV went 24 -> 73 -> 106 ms. The test counts iterations over ``student.scores`` instead of timing,
so it is deterministic on a loaded CI box.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from superteacher import reports
from superteacher.models import AssessmentKind, AttendanceStatus

TODAY = date(2026, 3, 1)


class CountingList(list):
    iterations = 0

    def __iter__(self):
        CountingList.iterations += 1
        return super().__iter__()


def _school(n_students: int, n_assessments: int):
    kinds = list(AssessmentKind)
    assessments = [
        SimpleNamespace(
            id=f"a{i}",
            title=f"Task {i}",
            kind=kinds[i % len(kinds)],
            due_date=TODAY - timedelta(days=n_assessments - i),
            max_points=100.0,
        )
        for i in range(n_assessments)
    ]
    students = []
    for j in range(n_students):
        scores = CountingList(
            SimpleNamespace(
                assessment_id=a.id,
                assessment=a,
                # a deterministic mix of graded and not-yet-submitted work
                points=None if (i + j) % 7 == 0 else float(50 + (i * 3 + j * 5) % 50),
            )
            for i, a in enumerate(assessments)
        )
        attendance = [
            SimpleNamespace(
                day=TODAY - timedelta(days=d), status=AttendanceStatus.present if d % 9 else AttendanceStatus.absent
            )
            for d in range(10)
        ]
        students.append(
            SimpleNamespace(id=f"s{j}", name=f"Student {j}", scores=scores, attendance=attendance, notes=[])
        )
    section = SimpleNamespace(
        id="sec", name="Period 1", course=SimpleNamespace(name="Algebra"), assessments=assessments
    )
    return section, students


def test_class_summary_reads_each_students_scores_a_constant_number_of_times():
    section, students = _school(n_students=40, n_assessments=120)
    CountingList.iterations = 0
    reports.class_summary(section, students, TODAY)
    # metrics.compute reads scores once per student, the summary builds its lookup map once: 2 each.
    # The quadratic version read them once more per assessment (40 * (120 + 1) iterations).
    assert CountingList.iterations <= 2 * len(students)


def test_class_summary_assessment_stats_match_a_brute_force_computation():
    section, students = _school(n_students=15, n_assessments=12)
    summary = reports.class_summary(section, students, TODAY)
    assert [a.id for a in summary.assessments] == [a.id for a in section.assessments]
    for stat, a in zip(summary.assessments, section.assessments, strict=True):
        pts = [sc.points for s in students for sc in s.scores if sc.assessment_id == a.id]
        graded = [p for p in pts if p is not None]
        assert stat.graded == len(graded)
        expected_avg = round(sum(graded) / len(graded), 1) if graded else None
        assert stat.average == expected_avg
        if a.due_date <= TODAY:
            assert stat.missing_pct == round((len(pts) - len(graded)) / len(pts) * 100, 1)
