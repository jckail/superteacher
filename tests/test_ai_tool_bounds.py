"""Tool output budgets must preserve complete JSON records and honest counts."""

import copy
import json

import pytest

from superteacher import ai_tools


def wide_rows(count):
    return [
        {
            "id": f"student{i:05d}",
            "name": "界" * 80,
            "grade": 9,
            "course": "界" * 60,
            "section": "界" * 40,
            "average": 60.0,
            "letter": "D",
            "trend": -8.0,
            "attendance": 75.0,
            "homework": 60.0,
            "missing": 3,
            "status": "at_risk",
            "flags": ["flag" * 30] * 4,
        }
        for i in range(count)
    ]


def test_execute_find_keeps_complete_ranked_students_and_match_count(monkeypatch):
    rows = wide_rows(25)
    result = {"total_matches": 200, "returned": 25, "students": rows}
    monkeypatch.setattr(ai_tools, "iter_summaries", lambda *args, **kwargs: iter(()))
    monkeypatch.setattr(ai_tools, "_find_summaries", lambda *args: result)
    text = ai_tools.execute(None, "find_students", {})
    payload = json.loads(text)
    assert len(text) <= ai_tools.MAX_TOOL_RESULT_CHARS
    assert payload["total_matches"] == 200
    assert 0 < payload["returned"] < 25
    assert payload["students"] == rows[: payload["returned"]]
    assert payload["omitted"] == {"students": 25 - payload["returned"]}
    assert payload["truncated"] is True


@pytest.mark.parametrize("name,key", [("class_stats", "sections"), ("get_student", "candidates")])
def test_execute_other_structured_results_preserve_records_and_aggregates(monkeypatch, name, key):
    rows = (
        wide_rows(10)
        if key == "candidates"
        else [
            {
                "section": f"{i:02d} " + "界" * 100,
                "students": 10,
                "average": 60.0,
                "at_risk": 2,
                "unknown": 1,
                "status_counts": {"unknown": 1, "on_track": 7, "watch": 0, "at_risk": 2},
            }
            for i in range(10)
        ]
    )
    result = {key: rows, "average": 60.0}
    if name == "class_stats":
        result["students"] = 100
        monkeypatch.setattr(ai_tools, "iter_summaries", lambda *args, **kwargs: iter(()))
        monkeypatch.setattr(ai_tools, "_class_summaries", lambda *args: result)
    else:
        result["error"] = "Several students match; call again with student_id."
        monkeypatch.setattr(ai_tools, "_get_student", lambda *args: result)
    monkeypatch.setattr(ai_tools, "MAX_TOOL_RESULT_CHARS", 2000)
    text = ai_tools.execute(None, name, {})
    payload = json.loads(text)
    assert len(text) <= 2000
    assert 0 < len(payload[key]) < len(rows)
    assert payload[key] == rows[: len(payload[key])]
    assert payload["omitted"][key] == len(rows) - len(payload[key])
    assert payload["average"] == 60.0
    if name == "class_stats":
        assert payload["students"] == 100
    else:
        assert payload["error"] == result["error"]


def test_oversized_record_is_omitted_whole_without_mutating_input():
    result = {"total_matches": 1, "returned": 1, "students": [{"name": "界" * 15000}]}
    original = copy.deepcopy(result)
    payload = json.loads(ai_tools._serialize_result(result))
    assert payload == {"total_matches": 1, "returned": 0, "students": [], "truncated": True, "omitted": {"students": 1}}
    assert result == original


def test_small_unicode_structured_result_preserves_values_and_counts():
    result = {"total_matches": 1, "returned": 1, "students": [{"id": "s", "name": "İpek"}]}
    assert json.loads(ai_tools._serialize_result(result)) == result


def test_oversized_student_record_returns_json_error_without_partial_tags():
    record = "<student_record>" + "x" * ai_tools.MAX_TOOL_RESULT_CHARS + "</student_record>"
    text = ai_tools._serialize_result(record)
    assert len(text) <= ai_tools.MAX_TOOL_RESULT_CHARS
    assert json.loads(text) == {
        "error": "Student record exceeds the output limit; no partial record was returned.",
        "truncated": True,
    }
    assert "<student_record>" not in text
    exact = "x" * ai_tools.MAX_TOOL_RESULT_CHARS
    assert ai_tools._serialize_result(exact) == exact
