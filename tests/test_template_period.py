"""A cumulative trend must not claim a term that the data model does not have."""

from datetime import date
from types import SimpleNamespace

import pytest

from superteacher import metrics, reports
from superteacher.models import AssessmentKind


@pytest.mark.parametrize("tone", ["warm", "neutral", "concerned"])
def test_improving_template_does_not_invent_a_term(tone):
    points = [
        metrics.make_point(str(i), f"Quiz{i}", AssessmentKind.quiz, date(2026, 9, i + 1), 100, value)
        for i, value in enumerate([0, 100, 100, 100])
    ]
    measured = metrics.compute_from(points, [], date(2026, 9, 30))
    assert measured.trend == 100
    student = SimpleNamespace(name="Alex Smith", section=SimpleNamespace(course=SimpleNamespace(name="Math")))
    draft = reports.template_draft(student, measured, tone)
    assert "recent work has improved compared with earlier work" in draft.body
    assert "earlier in the term" not in draft.body
