"""Invalid tool arguments must fail before querying classroom data."""

import asyncio
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from superteacher import ai, ai_tools
from superteacher.models import OWNER_ID


@pytest.fixture
def no_lookup(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Invalid arguments reached classroom lookup")

    monkeypatch.setattr(ai_tools, "iter_summaries", fail)
    monkeypatch.setattr(ai_tools, "_get_student", fail)


@pytest.mark.parametrize("name", sorted(ai_tools.TOOL_NAMES))
@pytest.mark.parametrize("value", [None, [], ["Ada"], "Ada", 0, False])
def test_nonobject_arguments_fail_before_lookup(no_lookup, name, value):
    with pytest.raises(ai_tools.ToolError, match="expected an object"):
        ai_tools.execute(None, name, value, owner_id=OWNER_ID)


@pytest.mark.parametrize(
    "name,args",
    [
        ("find_students", {"min_attendance": 90}),
        ("find_students", {"name": "Ada"}),
        ("get_student", {"student_id": "ada", "section": "Period 1"}),
        ("class_stats", {"section_id": "section"}),
    ],
)
def test_unsupported_filters_fail_before_lookup(no_lookup, name, args):
    with pytest.raises(ai_tools.ToolError, match="Extra inputs are not permitted"):
        ai_tools.execute(None, name, args, owner_id=OWNER_ID)


@pytest.mark.parametrize("field", ["max_average", "min_average", "max_attendance"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity"])
def test_nonfinite_filters_fail_before_lookup(no_lookup, field, value):
    with pytest.raises(ai_tools.ToolError, match="finite number"):
        ai_tools.execute(None, "find_students", {field: value}, owner_id=OWNER_ID)


def test_valid_finite_filters_and_coercion_remain_supported():
    args = ai_tools.FindStudentsArgs.model_validate(
        {"max_average": "125.5", "min_average": -5, "max_attendance": "90", "limit": "25"}
    )
    assert (args.max_average, args.min_average, args.max_attendance, args.limit) == (125.5, -5, 90, 25)
    assert ai_tools.FindStudentsArgs().limit == 15
    assert ai_tools.GetStudentArgs(student_id="ada", name="Ada").student_id == "ada"
    assert ai_tools.ClassStatsArgs().section is None


@pytest.mark.parametrize("legacy", [False, True])
def test_existing_owner_call_forms_are_preserved(monkeypatch, legacy):
    calls = []

    def summaries(db, **kwargs):
        calls.append(kwargs)
        return iter(())

    monkeypatch.setattr(ai_tools, "iter_summaries", summaries)
    args = {"section": "Period 1", "name_contains": "Ada", "max_average": 80, "sort_by": "average", "limit": 5}
    if legacy:
        result = ai_tools.execute(None, "owner-example", "find_students", args)
    else:
        result = ai_tools.execute(None, "find_students", args, owner_id="owner-example")
    assert json.loads(result) == {"total_matches": 0, "returned": 0, "students": []}
    assert calls == [
        {"owner_id": "owner-example", "section": "Period 1", "name_contains": "Ada", "retain_scores": False}
    ]


def test_invalid_arguments_are_model_visible_errors(no_lookup):
    block = SimpleNamespace(id="lookup", name="find_students", input={"min_attendance": 90})
    result = asyncio.run(ai._run_tool(lambda: nullcontext(None), OWNER_ID, block))
    assert result["tool_use_id"] == "lookup" and result["is_error"] is True
    assert "Invalid arguments" in result["content"]
