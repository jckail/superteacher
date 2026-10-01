import pytest

from superteacher.metrics import letter_and_gpa


@pytest.mark.parametrize(
    "pct,letter,gpa", [(100, "A", 4.0), (93, "A", 4.0), (92.9, "A-", 3.7), (80, "B-", 2.7), (59, "F", 0.0)]
)
def test_letter_bands(pct, letter, gpa):
    assert letter_and_gpa(pct) == (letter, gpa)


def test_no_data_gives_none():
    assert letter_and_gpa(None) == (None, None)


# ── property-style tests ───────────────────────────────────────────────────
import random  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from superteacher.metrics import KIND_WEIGHTS, compute_from, make_point  # noqa: E402
from superteacher.models import AssessmentKind, AttendanceStatus  # noqa: E402

TODAY = date(2026, 6, 1)


def _rand_points(rng, n, allow_future=True):
    out = []
    for i in range(n):
        mx = rng.choice([1, 5, 10, 25, 100, 0.5])
        pts = rng.choice([None, rng.uniform(0, mx), 0, mx])
        due = TODAY + timedelta(days=rng.randint(-40, 10 if allow_future else 0))
        out.append(make_point(f"a{i}", f"T{i}", rng.choice(list(AssessmentKind)), due, mx, pts))
    return out


def test_average_always_within_0_100():
    rng = random.Random(1)
    for _ in range(300):
        m = compute_from(_rand_points(rng, rng.randint(0, 12)), [], TODAY)
        assert m.average is None or 0 <= m.average <= 100.0000001
        assert m.homework_rate is None or 0 <= m.homework_rate <= 100
        assert m.missing >= 0


def test_future_work_never_affects_anything():
    rng = random.Random(2)
    for _ in range(100):
        pts = _rand_points(rng, 8)
        due_only = [p for p in pts if p.due_date <= TODAY]
        a, b = compute_from(pts, [], TODAY), compute_from(due_only, [], TODAY)
        assert (a.average, a.trend, a.missing, a.homework_rate, a.risk) == (
            b.average,
            b.trend,
            b.missing,
            b.homework_rate,
            b.risk,
        )


def test_weights_renormalise_over_present_kinds():
    assert abs(sum(KIND_WEIGHTS.values()) - 1) < 1e-9
    p = [
        make_point("1", "t", AssessmentKind.test, TODAY, 100, 80),
        make_point("2", "h", AssessmentKind.homework, TODAY, 10, 10),
    ]
    m = compute_from(p, [], TODAY)
    assert m.average == pytest.approx((0.40 * 80 + 0.25 * 100) / 0.65)


def test_zero_max_points_is_safe():
    m = compute_from([make_point("1", "t", AssessmentKind.test, TODAY, 0, 0)], [], TODAY)
    assert m.average is None and m.scores[0].pct is None


def test_lower_scores_never_lower_risk():
    """Risk is monotone: replacing every score with a worse one cannot improve the risk level."""
    order = {"on_track": 0, "watch": 1, "at_risk": 2}
    rng = random.Random(3)
    for _ in range(200):
        pts = _rand_points(rng, 8, allow_future=False)
        st = [rng.choice(list(AttendanceStatus)) for _ in range(rng.randint(0, 10))]
        worse = [
            make_point(
                p.assessment_id, p.title, p.kind, p.due_date, p.max_points, None if p.points is None else p.points * 0.5
            )
            for p in pts
        ]
        a, b = compute_from(pts, st, TODAY), compute_from(worse, st, TODAY)
        if a.average is not None and b.average is not None:
            assert b.average <= a.average + 1e-9
            # Trend can legitimately improve when halving flattens a drop, so compare average-only risk.
            if a.trend is None and b.trend is None:
                assert order[b.risk] >= order[a.risk]


def test_attendance_excused_only_and_empty():
    assert compute_from([], [AttendanceStatus.excused] * 3, TODAY).attendance_rate is None
    m = compute_from([], [AttendanceStatus.absent, AttendanceStatus.present], TODAY)
    assert m.attendance_rate == 50 and m.absences == 1


def test_trend_window_and_ties_deterministic():
    pts = [
        make_point(f"{i}", f"T{i}", AssessmentKind.quiz, TODAY - timedelta(days=10 - i), 100, v)
        for i, v in enumerate([90, 90, 60, 60, 60])
    ]
    assert compute_from(pts, [], TODAY).trend == pytest.approx(-30)
    assert compute_from(list(reversed(pts)), [], TODAY).trend == pytest.approx(-30)
