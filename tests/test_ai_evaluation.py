"""Offline answer evaluation must detect regressions without claiming model safety."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures/ai_grounding"


def replay(tmp_path, bundle=None, *, output=None):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(bundle or json.loads((FIXTURES / "example_answers.json").read_text())))
    output = output or tmp_path / "report.json"
    run = subprocess.run(
        [sys.executable, "-m", "superteacher.evaluate_ai", "--answers", str(path), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return run, output


def example():
    return json.loads((FIXTURES / "example_answers.json").read_text())


def test_synthetic_gold_replay_has_hashed_private_report_and_requires_human_review(tmp_path):
    result, output = replay(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["provenance"] == "synthetic"
    assert report["automated_checks"] == "passed"
    assert report["human_review_required"] is True
    assert report["real_model_acceptance"] == "not_established"
    assert report["replay_provider_calls"] == 0
    assert len(report["cases"]) == 6
    assert all(len(case["answer_sha256"]) == 64 for case in report["cases"])
    assert output.stat().st_mode & 0o777 == 0o600
    assert "Ada" not in output.read_text() and "79%" not in output.read_text()


def test_numeric_claim_in_wrong_context_is_flagged_even_if_value_exists_in_gold(tmp_path):
    bundle = example()
    bundle["answers"][0]["answer"] += " Attendance is 79%."
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 1, result.stderr
    assert "uncovered_numeric_claim" in json.loads(output.read_text())["cases"][0]["findings"]


def test_wrong_value_and_missing_required_fact_fail(tmp_path):
    bundle = example()
    bundle["answers"][0]["answer"] = "Ada Rivera's average is 98%, with a letter grade of A."
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 1, result.stderr
    assert "required_fact_missing:average" in json.loads(output.read_text())["cases"][0]["findings"]


def test_private_note_and_peer_disclosure_are_flagged_without_copying_them_to_report(tmp_path):
    bundle = example()
    bundle["answers"][4]["answer"] += " PEER_ONLY Morgan told me PRIVATE_ONLY confidential conference detail."
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_text())
    assert "forbidden_identifier" in report["cases"][4]["findings"]
    assert "PRIVATE_ONLY" not in output.read_text() and "Morgan" not in output.read_text()


def test_unicode_and_spelled_number_claims_do_not_evade_checks(tmp_path):
    bundle = example()
    bundle["answers"][0]["answer"] += " Attendance is \uff19\uff19%. There are ten missing assignments."
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 1, result.stderr
    assert "uncovered_numeric_claim" in json.loads(output.read_text())["cases"][0]["findings"]


def test_existing_report_is_never_overwritten(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("keep")
    result, _ = replay(tmp_path, output=output)
    assert result.returncode == 2
    assert output.read_text() == "keep"


def test_missing_and_duplicate_cases_are_input_failures(tmp_path):
    bundle = example()
    bundle["answers"][-1] = bundle["answers"][0]
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 2 and not output.exists()


@pytest.mark.parametrize("raw", ["[" * 2000 + "0" + "]" * 2000, '{"provenance":"synthetic","provenance":"capture"}'])
def test_malformed_capture_is_a_clean_input_failure(tmp_path, raw):
    path = tmp_path / "answers.json"
    path.write_text(raw)
    output = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "-m", "superteacher.evaluate_ai", "--answers", str(path), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2 and "Traceback" not in result.stderr and not output.exists()


def test_output_symlink_cannot_replace_or_expose_target(tmp_path):
    target = tmp_path / "private-existing"
    target.write_text("keep")
    output = tmp_path / "report.json"
    output.symlink_to(target)
    result, _ = replay(tmp_path, output=output)
    assert result.returncode == 2
    assert target.read_text() == "keep" and output.is_symlink()


def test_fixture_drift_requires_adjudication_before_scoring():
    from superteacher.evaluate_ai import EvaluationError, evaluate

    rubric = json.loads((FIXTURES / "questions.json").read_text())
    classroom = json.loads((FIXTURES / "classroom.json").read_text())
    classroom["expected"]["average"] = 99
    with pytest.raises(EvaluationError, match="adjudicate"):
        evaluate(example(), rubric, classroom)


@pytest.mark.parametrize("mutation", ["missing", "unknown", "oversize", "wrong-provenance"])
def test_invalid_bundle_never_creates_a_report(tmp_path, mutation):
    bundle = example()
    if mutation == "missing":
        bundle["answers"].pop()
    elif mutation == "unknown":
        bundle["answers"][0]["case_id"] = "unknown"
    elif mutation == "oversize":
        bundle["answers"][0]["answer"] = "x" * 8001
    else:
        bundle["provenance"] = "verified_provider"
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 2 and not output.exists()


def test_replay_never_uses_network_or_application_database(tmp_path, monkeypatch):
    import socket

    from superteacher.evaluate_ai import main

    def forbidden_network(*args, **kwargs):
        raise AssertionError("Offline evaluation attempted a provider/network request")

    monkeypatch.setattr(socket, "socket", forbidden_network)
    app_db = tmp_path / "should-not-exist.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{app_db}")
    output = tmp_path / "report.json"
    assert main(["--answers", str(FIXTURES / "example_answers.json"), "--output", str(output)]) == 0
    assert not app_db.exists()


def test_unknown_names_and_semantic_claims_still_require_human_review(tmp_path):
    bundle = example()
    bundle["answers"][0]["answer"] += " Taylor has an excellent attitude."
    result, output = replay(tmp_path, bundle)
    assert result.returncode == 0
    assert json.loads(output.read_text())["human_review_required"] is True
