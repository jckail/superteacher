"""Offline artifact contracts; no app, database, benchmark, or provider execution."""

import argparse
import ast
import copy
import importlib.util
import json
import resource
import statistics
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "bench_budgets", Path(__file__).parents[1] / "scripts/check_bench_budgets.py"
)
budgets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budgets)
POLICY = budgets.load(budgets.DEFAULT_POLICY)


@pytest.fixture
def report():
    return {
        "sizes": [
            {
                "size": POLICY["size"],
                "dataset": copy.deepcopy(POLICY["dataset"]),
                "results": [
                    {"case": name, "runs": POLICY["minimum_runs"], **limits} for name, limits in POLICY["cases"].items()
                ],
            }
        ]
    }


def test_all_cases_and_metrics_pass_at_the_inclusive_boundary(report):
    for row in report["sizes"][0]["results"]:
        for metric in budgets.METRICS:
            row[metric] *= 1 + POLICY["tolerance"][metric]
            if metric == "sql_statements":
                row[metric] = int(row[metric])
    assert budgets.check(report, POLICY) == []


@pytest.mark.parametrize("name", POLICY["cases"])
@pytest.mark.parametrize("metric", budgets.METRICS)
def test_each_endpoint_and_metric_regression_is_reported(report, name, metric):
    row = next(x for x in report["sizes"][0]["results"] if x["case"] == name)
    row[metric] = POLICY["cases"][name][metric] * (1 + POLICY["tolerance"][metric]) + 1
    if metric == "sql_statements":
        row[metric] = int(row[metric])
    failures = budgets.check(report, POLICY)
    assert len(failures) == 1
    assert name in failures[0] and metric in failures[0] and "exceeds" in failures[0]


@pytest.mark.parametrize("bad", [None, True, -1, float("nan"), float("inf"), "1", 10**400])
@pytest.mark.parametrize("metric", budgets.METRICS)
def test_missing_or_invalid_metrics_cannot_pass(report, metric, bad):
    report["sizes"][0]["results"][0][metric] = bad
    with pytest.raises(ValueError, match="expected a finite"):
        budgets.check(report, POLICY)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unbudgeted", "short-sample", "fractional-sql"])
def test_partial_or_changed_case_coverage_cannot_pass(report, defect):
    rows = report["sizes"][0]["results"]
    if defect == "missing":
        rows.pop()
    elif defect == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif defect == "unbudgeted":
        rows[0]["case"] = "new endpoint without budget"
    elif defect == "short-sample":
        rows[0]["runs"] = POLICY["minimum_runs"] - 1
    else:
        rows[0]["sql_statements"] = 1.5
    with pytest.raises(ValueError):
        budgets.check(report, POLICY)


@pytest.mark.parametrize("defect", ["empty", "extra", "wrong-size", "missing-count", "changed-count"])
def test_unqualified_dataset_cannot_pass(report, defect):
    block = report["sizes"][0]
    if defect == "empty":
        report["sizes"] = []
    elif defect == "extra":
        report["sizes"].append(copy.deepcopy(block))
    elif defect == "wrong-size":
        block["size"] = 5000
    elif defect == "missing-count":
        del block["dataset"]["students"]
    else:
        block["dataset"]["students"] -= 1
    with pytest.raises(ValueError):
        budgets.check(report, POLICY)


@pytest.mark.parametrize(
    "defect",
    ["version", "boolean-version", "tolerance", "missing-metric", "negative-limit", "empty-cases", "overflow-limit"],
)
def test_invalid_policy_is_refused(report, defect):
    policy = copy.deepcopy(POLICY)
    first = next(iter(policy["cases"].values()))
    if defect == "version":
        policy["version"] = 2
    elif defect == "boolean-version":
        policy["version"] = True
    elif defect == "tolerance":
        policy["tolerance"]["p95_ms"] = float("inf")
    elif defect == "missing-metric":
        del first["peak_mem_mb"]
    elif defect == "negative-limit":
        first["p95_ms"] = -1
    elif defect == "overflow-limit":
        first["p95_ms"] = 1e308
        policy["tolerance"]["p95_ms"] = 1e308
    else:
        policy["cases"] = {}
    with pytest.raises(ValueError):
        budgets.check(report, policy)


def test_cli_distinguishes_pass_budget_failure_and_invalid_evidence(report, tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert budgets.main([str(path)]) == 0
    assert "passed" in capsys.readouterr().out
    report["sizes"][0]["results"][0]["p95_ms"] = 999999
    path.write_text(json.dumps(report))
    assert budgets.main([str(path)]) == 1
    assert "budget exceeded" in capsys.readouterr().err
    report["sizes"][0]["results"][0]["p95_ms"] = 10**400
    path.write_text(json.dumps(report))
    assert budgets.main([str(path)]) == 2
    assert "Traceback" not in capsys.readouterr().err
    path.write_text('{"sizes": [], "sizes": []}')
    assert budgets.main([str(path)]) == 2
    assert "Duplicate JSON key" in capsys.readouterr().err


def test_measure_keeps_earlier_and_memory_query_spikes():
    # Compile the live benchmark function only; importing bench.py would import
    # the application and change its environment. No app or database is needed.
    path = Path(__file__).parents[1] / "scripts/bench.py"
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"measure", "pct"}]
    namespace = {
        "Callable": Callable,
        "Counter": SimpleNamespace,
        "statistics": statistics,
        "time": time,
        "tracemalloc": tracemalloc,
        "resource": resource,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    counter = SimpleNamespace(n=0)
    for counts, memory, expected in [([9, 3, 2], False, 9), ([1, 2, 1, 11], True, 11)]:
        values = iter(counts)

        def operation(values=values):
            counter.n += next(values)
            return 1

        result = namespace["measure"]("inert", operation, counter, runs=3, warmup=0, mem=memory)
        assert result["sql_statements"] == expected


@pytest.mark.parametrize("probe_seconds", [0, 2.999, 3, 19.999, 20, 120])
def test_fixed_runs_preserves_budget_sample_count(probe_seconds):
    path = Path(__file__).parents[1] / "scripts/bench.py"
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "measurement_plan"]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    assert namespace["measurement_plan"](probe_seconds, 15, 2, fixed_runs=True) == (15, 2)


@pytest.mark.parametrize("probe_seconds, expected", [(2, (15, 2)), (3, (5, 2)), (20, (3, 0))])
def test_adaptive_sweeps_keep_existing_sample_policy(probe_seconds, expected):
    path = Path(__file__).parents[1] / "scripts/bench.py"
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "measurement_plan"]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    assert namespace["measurement_plan"](probe_seconds, 15, 2) == expected


@pytest.mark.parametrize("fixed", [False, True])
def test_cli_forwards_fixed_run_selection(monkeypatch, fixed):
    path = Path(__file__).parents[1] / "scripts/bench.py"
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    calls = []
    namespace = {
        "__doc__": "inert CLI fixture",
        "argparse": argparse,
        "datetime": datetime,
        "UTC": UTC,
        "_quiet_logs": lambda: None,
        "machine": lambda: {},
        "markdown": lambda _: "",
        "run_size": lambda *args, **kwargs: calls.append((args, kwargs)) or {},
    }
    monkeypatch.setattr("sys.argv", ["bench.py", "--runs", "15"] + (["--fixed-runs"] if fixed else []))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    namespace["main"]()
    assert len(calls) == 1
    assert calls[0][0][1] == 15
    assert calls[0][1]["fixed_runs"] is fixed


def test_slow_probe_inert_measurement_and_budget_interaction(report):
    path = Path(__file__).parents[1] / "scripts/bench.py"
    tree = ast.parse(path.read_text())
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"measurement_plan", "measure", "pct"}
    ]
    namespace = {
        "Callable": Callable,
        "Counter": SimpleNamespace,
        "statistics": statistics,
        "time": time,
        "tracemalloc": tracemalloc,
        "resource": resource,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    row = report["sizes"][0]["results"][0]
    for fixed in [False, True]:
        runs, warmup = namespace["measurement_plan"](3.1, 15, 0, fixed_runs=fixed)
        measured = namespace["measure"](row["case"], lambda: None, SimpleNamespace(n=0), runs, warmup, mem=True)
        row.update(measured)
        if fixed:
            assert row["runs"] == 15
            assert budgets.check(report, POLICY) == []
        else:
            assert row["runs"] == 5
            with pytest.raises(ValueError, match="requires at least 15 measured runs"):
                budgets.check(report, POLICY)
