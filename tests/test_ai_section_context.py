"""Colliding readable labels must not merge AI roster section summaries."""

from datetime import date
from types import SimpleNamespace

import pytest

from superteacher import ai


def summaries(reverse=False, collision=True):
    rows = []
    for sid, suffix, average, risk in [("sec-z", "X", 10, "at_risk"), ("sec-a", "Y", 90, "on_track")]:
        name = "A" * 40 + suffix if collision else suffix
        section = SimpleNamespace(id=sid, name=name, course=SimpleNamespace(name="Algebra"))
        student = SimpleNamespace(id=sid + "-student", name=suffix, grade_level=7, section_id=sid, section=section)
        metric = SimpleNamespace(
            average=average,
            attendance_rate=None,
            homework_rate=None,
            missing=0,
            risk=risk,
            letter="F" if average == 10 else "A-",
            trend=None,
            risk_reasons=[],
        )
        rows.append((student, metric))
    return rows[::-1] if reverse else rows


@pytest.mark.parametrize("reverse", [False, True])
def test_colliding_section_labels_have_distinct_context_metrics(monkeypatch, reverse):
    monkeypatch.setattr(ai, "iter_summaries", lambda *a, **k: iter(summaries(reverse)))
    monkeypatch.setattr(ai, "setting_int", lambda *a: 1)
    monkeypatch.setattr(ai, "school_today", lambda: date(2026, 10, 1))
    roster, focus = ai.build_context_parts(None)
    label = "Algebra / " + "A" * 39 + "…"
    lines = [line for line in roster.splitlines() if line.startswith("- " + label)]
    assert lines == [
        f"- {label} (section id sec-a): 1 students, avg 90%",
        f"- {label} (section id sec-z): 1 students, avg 10%",
    ]
    assert focus == ""


def test_unique_section_labels_preserve_context_wording(monkeypatch):
    monkeypatch.setattr(ai, "iter_summaries", lambda *a, **k: iter(summaries(collision=False)))
    monkeypatch.setattr(ai, "setting_int", lambda *a: 1)
    roster, _ = ai.build_context_parts(None)
    assert "- Algebra / X: 1 students, avg 10%" in roster
    assert "- Algebra / Y: 1 students, avg 90%" in roster
    assert "section id" not in roster
