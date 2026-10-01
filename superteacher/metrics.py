"""Derived student metrics. Pure functions over ORM rows — nothing here touches the DB.

One definition of "grade", "attendance" and "risk", shared by the roster, the
detail view, the overview and the AI context, so the numbers never disagree.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from statistics import mean

from .models import AssessmentKind, AttendanceStatus, Student

# Category weights for the course average; renormalised over categories that have data.
KIND_WEIGHTS = {
    AssessmentKind.test: 0.40,
    AssessmentKind.quiz: 0.20,
    AssessmentKind.homework: 0.25,
    AssessmentKind.project: 0.15,
}

_LETTERS = [
    (93, "A", 4.0), (90, "A-", 3.7), (87, "B+", 3.3), (83, "B", 3.0), (80, "B-", 2.7),
    (77, "C+", 2.3), (73, "C", 2.0), (70, "C-", 1.7), (60, "D", 1.0), (0, "F", 0.0),
]  # fmt: skip


def mean_of(values: Iterable[float | None]) -> float | None:
    """Mean of the values that are present; None when there are none."""
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def letter_and_gpa(pct: float | None) -> tuple[str | None, float | None]:
    if pct is None:
        return None, None
    for floor, letter, gpa in _LETTERS:
        if pct >= floor:
            return letter, gpa
    return "F", 0.0


@dataclass
class ScorePoint:
    assessment_id: str
    title: str
    kind: AssessmentKind
    due_date: date
    max_points: float
    points: float | None
    pct: float | None


@dataclass
class StudentMetrics:
    average: float | None = None  # 0-100
    letter: str | None = None
    gpa: float | None = None
    trend: float | None = None  # recent-3 minus earlier average, in points
    attendance_rate: float | None = None  # 0-100
    absences: int = 0
    tardies: int = 0
    homework_rate: float | None = None  # 0-100, of homework already due
    missing: int = 0
    risk: str = "on_track"  # on_track | watch | at_risk
    risk_reasons: list[str] = field(default_factory=list)
    scores: list[ScorePoint] = field(default_factory=list)


def make_point(
    aid: str, title: str, kind: AssessmentKind, due: date, max_points: float, points: float | None
) -> ScorePoint:
    pct = None if points is None or not max_points else points / max_points * 100
    return ScorePoint(aid, title, kind, due, max_points, points, pct)


def _sort(points: list[ScorePoint]) -> list[ScorePoint]:
    # Total order (not just due_date) so the trend window is deterministic for same-day assessments.
    return sorted(points, key=lambda s: (s.due_date, s.title, s.assessment_id))


def score_points(student: Student, today: date | None = None) -> list[ScorePoint]:
    return _sort(
        [make_point(sc.assessment.id, sc.assessment.title, sc.assessment.kind, sc.assessment.due_date,
                    sc.assessment.max_points, sc.points) for sc in student.scores]
    )  # fmt: skip


def compute(student: Student, today: date | None = None) -> StudentMetrics:
    return compute_from(score_points(student), [a.status for a in student.attendance], today)


def compute_from(
    points: list[ScorePoint], statuses: list[AttendanceStatus], today: date | None = None
) -> StudentMetrics:
    """Same as :func:`compute` but over plain values, so bulk callers can skip ORM hydration."""
    today = today or date.today()
    m = StudentMetrics(scores=_sort(points))
    due = [s for s in m.scores if s.due_date <= today]
    graded = [s for s in due if s.pct is not None]

    # Weighted average across assessment kinds.
    by_kind: dict[AssessmentKind, list[ScorePoint]] = {}
    for s in graded:
        by_kind.setdefault(s.kind, []).append(s)
    if by_kind:
        weights = {k: KIND_WEIGHTS[k] for k in by_kind}
        total_w = sum(weights.values())
        m.average = sum(
            weights[k] / total_w * (sum(s.points for s in v) / sum(s.max_points for s in v) * 100)
            for k, v in by_kind.items()
        )
        m.letter, m.gpa = letter_and_gpa(m.average)

    if len(graded) >= 4:
        recent, earlier = graded[-3:], graded[:-3]
        m.trend = mean(s.pct for s in recent) - mean(s.pct for s in earlier)

    hw_due = [s for s in due if s.kind is AssessmentKind.homework]
    m.missing = sum(1 for s in due if s.points is None)
    if hw_due:
        m.homework_rate = sum(1 for s in hw_due if s.points is not None) / len(hw_due) * 100

    counted = [st for st in statuses if st is not AttendanceStatus.excused]
    if counted:
        attended = sum(1 for st in counted if st in (AttendanceStatus.present, AttendanceStatus.tardy))
        m.attendance_rate = attended / len(counted) * 100
    m.absences = sum(1 for st in statuses if st is AttendanceStatus.absent)
    m.tardies = sum(1 for st in statuses if st is AttendanceStatus.tardy)

    _assess_risk(m)
    return m


def _assess_risk(m: StudentMetrics) -> None:
    points, why = 0, []
    if m.average is not None:
        if m.average < 65:
            points += 3
            why.append(f"Average {m.average:.0f}% is failing")
        elif m.average < 72:
            points += 2
            why.append(f"Average {m.average:.0f}% is below C-")
    if m.trend is not None and m.trend <= -8:
        points += 2 if m.trend <= -15 else 1
        why.append(f"Recent work is {abs(m.trend):.0f} points below earlier work")
    if m.attendance_rate is not None:
        if m.attendance_rate < 80:
            points += 2
            why.append(f"Attendance {m.attendance_rate:.0f}%")
        elif m.attendance_rate < 90:
            points += 1
            why.append(f"Attendance {m.attendance_rate:.0f}%")
    if m.homework_rate is not None and m.homework_rate < 70:
        points += 1
        why.append(f"Homework completion {m.homework_rate:.0f}%")
    # A single soft signal (one tardy-ish week, one bad quiz) is noise; two together are a pattern.
    m.risk = "at_risk" if points >= 3 else "watch" if points >= 2 else "on_track"
    m.risk_reasons = why


def fingerprint(student: Student, m: StudentMetrics) -> str:
    """Stable hash of everything an AI insight depends on, to cache it until the data moves."""
    parts = [student.name, str(student.grade_level), f"{m.average}", f"{m.attendance_rate}", f"{m.homework_rate}"]
    parts += [f"{s.assessment_id}:{s.points}" for s in m.scores]
    parts += [n.id for n in student.notes]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
