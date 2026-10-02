"""Validate offline benchmark artifacts without importing or running the application."""

import argparse
import json
import math
import sys
from pathlib import Path

METRICS = ("p95_ms", "sql_statements", "peak_mem_mb")
DEFAULT_POLICY = Path(__file__).with_name("bench_budgets.json")


def number(value, label, *, integer=False, positive=False):
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value >= 0
            and (not positive or value > 0)
            and (not integer or isinstance(value, int))
        )
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label}: expected a finite {'positive' if positive else 'nonnegative'} number")
    return value


def check(report, policy):
    """Return budget violations; invalid or incomplete evidence raises ValueError."""
    if not isinstance(policy, dict) or type(policy.get("version")) is not int or policy["version"] != 1:
        raise ValueError("Unsupported budget policy")
    size = number(policy.get("size"), "policy.size", integer=True, positive=True)
    minimum = number(policy.get("minimum_runs"), "policy.minimum_runs", integer=True, positive=True)
    tolerance = policy.get("tolerance")
    cases = policy.get("cases")
    dataset = policy.get("dataset")
    if not isinstance(tolerance, dict) or set(tolerance) != set(METRICS):
        raise ValueError("Policy requires a tolerance for every metric")
    for metric in METRICS:
        number(tolerance[metric], f"tolerance.{metric}")
    if not isinstance(cases, dict) or not cases or not all(isinstance(name, str) and name for name in cases):
        raise ValueError("Policy requires named cases")
    if not isinstance(dataset, dict) or not dataset:
        raise ValueError("Policy requires dataset counts")
    for key, count in dataset.items():
        number(count, f"dataset.{key}", integer=True, positive=True)
    for name, limits in cases.items():
        if not isinstance(limits, dict) or set(limits) != set(METRICS):
            raise ValueError(f"{name}: policy requires all metrics")
        for metric in METRICS:
            number(limits[metric], f"{name}.{metric} limit", integer=metric == "sql_statements", positive=True)
    if not isinstance(report, dict) or not isinstance(report.get("sizes"), list) or len(report["sizes"]) != 1:
        raise ValueError("Report must contain exactly one budgeted dataset")
    block = report["sizes"][0]
    if not isinstance(block, dict) or block.get("size") != size:
        raise ValueError("Report dataset size differs from policy")
    observed = block.get("dataset")
    if not isinstance(observed, dict):
        raise ValueError("Report requires dataset counts")
    for key, count in dataset.items():
        if number(observed.get(key), f"report.dataset.{key}", integer=True) != count:
            raise ValueError(f"Report dataset count differs: {key}")
    results = block.get("results")
    if not isinstance(results, list):
        raise ValueError("Report requires case results")
    seen, violations = set(), []
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("case"), str):
            raise ValueError("Report contains an invalid case")
        name = row["case"]
        if name in seen or name not in cases:
            raise ValueError(f"Duplicate or unbudgeted case: {name}")
        seen.add(name)
        if number(row.get("runs"), f"{name}.runs", integer=True) < minimum:
            raise ValueError(f"{name}: requires at least {minimum} measured runs")
        for metric in METRICS:
            value = number(row.get(metric), f"{name}.{metric}", integer=metric == "sql_statements")
            allowed = number(cases[name][metric] * (1 + tolerance[metric]), f"{name}.{metric} tolerated limit")
            if value > allowed:
                violations.append(f"{name}: {metric} {value:g} exceeds {allowed:g}")
    if seen != set(cases):
        raise ValueError(f"Missing budgeted cases: {', '.join(sorted(set(cases) - seen))}")
    return violations


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(argv)
    try:
        violations = check(load(args.report), load(args.policy))
    except (OSError, ValueError) as exc:
        print(f"Benchmark evidence refused: {exc}", file=sys.stderr)
        return 2
    if violations:
        print("Benchmark budget exceeded:\n" + "\n".join(violations), file=sys.stderr)
        return 1
    print("Benchmark budgets passed for every case and metric.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
