"""Section statistics keep stable IDs even when readable labels collide."""

from types import SimpleNamespace

import pytest

from superteacher import ai_tools


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
def test_colliding_section_labels_have_distinct_statistics(reverse):
    output = ai_tools._class_summaries(iter(summaries(reverse)), ai_tools.ClassStatsArgs())
    assert output["students"] == 2 and output["average"] == 50
    assert [row["section_id"] for row in output["sections"]] == ["sec-a", "sec-z"]
    assert [row["average"] for row in output["sections"]] == [90, 10]
    assert [row["students"] for row in output["sections"]] == [1, 1]
    assert [row["at_risk"] for row in output["sections"]] == [0, 1]
    assert output["sections"][0]["section"] == output["sections"][1]["section"]


def test_existing_substring_filter_preserves_combined_aggregate():
    output = ai_tools._class_summaries(iter(summaries()), ai_tools.ClassStatsArgs(section="Algebra"))
    assert output["students"] == 2 and output["average"] == 50
    assert "sections" not in output
