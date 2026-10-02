"""Offline release checks: shared-replica staging and promotion require drain evidence."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def release(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gcloud"
    fake.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$RELEASE_LOG"\n'
        'case "$*" in\n'
        '  *"json(status)"*) revision=old; [ ! -f "$RELEASE_CHANGED" ] || revision=changed; '
        'printf \'{"status":{"traffic":[{"percent":100,"revisionName":"%s"}]}}\\n\' "$revision" ;;\n'
        '  *"builds submit"*) [ "${CHANGE_WRITER_AFTER_BUILD:-0}" != 1 ] || touch "$RELEASE_CHANGED" ;;\n'
        '  *"json(spec.containers)"*) case "${CANDIDATE_ENV_CASE:-match}" in\n'
        '    match) env=\'[{"name":"LITESTREAM_REPLICA_URL",'
        '"value":"gs://synthetic-project-superteacher-litestream/superteacher"}]\' ;;\n'
        '    mismatch) env=\'[{"name":"LITESTREAM_REPLICA_URL",'
        '"value":"gs://synthetic-project-superteacher-litestream/unrelated"}]\' ;;\n'
        "    missing) env='[]' ;;\n"
        '    duplicate) env=\'[{"name":"LITESTREAM_REPLICA_URL",'
        '"value":"gs://synthetic-project-superteacher-litestream/superteacher"},'
        '{"name":"LITESTREAM_REPLICA_URL",'
        '"value":"gs://synthetic-project-superteacher-litestream/superteacher"}]\' ;;\n'
        '    reference) env=\'[{"name":"LITESTREAM_REPLICA_URL",'
        '"valueFrom":{"secretKeyRef":{"name":"synthetic-secret","key":"1"}}}]\' ;;\n'
        '    empty) env=\'[{"name":"LITESTREAM_REPLICA_URL","value":""}]\' ;;\n'
        '    esac; printf \'{"spec":{"containers":[{"env":%s}]}}\\n\' "$env" ;;\n'
        "  *latestCreatedRevisionName*) echo superteacher-candidate ;;\n"
        '  *update-traffic*) exit "${PROMOTE_EXIT:-0}" ;;\n'
        "esac\n"
    )
    fake.chmod(0o700)
    log = tmp_path / "gcloud.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PROJECT": "synthetic-project",
        "SERVICE": "superteacher",
        "REPLICA_PREFIX": "superteacher",
        "RUNTIME_SERVICE_ACCOUNT": "synthetic@example.iam.gserviceaccount.com",
        "RELEASE_LOG": str(log),
        "RELEASE_CHANGED": str(tmp_path / "changed"),
    }
    env.pop("DRAINED_WRITER_CONFIRMED", None)
    env.pop("DRAINED_WRITER_REVISION", None)
    env.pop("ISOLATED_CANDIDATE_CONFIRMED", None)
    env.pop("CHANGE_WRITER_AFTER_BUILD", None)
    env.pop("CANDIDATE_ENV_CASE", None)

    def run(*args, **extra):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/deploy_cloud_run.sh"), *args],
            env={**env, **extra},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result, log.read_text() if log.exists() else ""

    return run


def test_isolated_stage_disables_initial_health_check_and_never_promotes(release):
    result, calls = release(
        "synthetic-commit",
        SERVICE="superteacher-overhaul-staging",
        REPLICA_PREFIX="overhaul-staging/synthetic-commit",
        ISOLATED_CANDIDATE_CONFIRMED="yes",
    )
    assert result.returncode == 0, result.stderr
    assert "--no-traffic --no-deploy-health-check" in calls
    assert "--min-instances 0 --min 0" in calls
    assert "FORWARDED_ALLOW_IPS=*" in calls
    assert "gs://synthetic-project-superteacher-litestream/overhaul-staging/synthetic-commit" in calls
    assert "update-traffic" not in calls and "--to-latest" not in calls
    assert "json(status)" not in calls


@pytest.mark.parametrize("setting", ["SERVICE", "REPLICA_PREFIX"])
def test_stage_requires_explicit_target_and_storage_before_any_cloud_call(release, setting):
    result, calls = release("synthetic-commit", **{setting: ""})
    assert result.returncode != 0
    assert setting in result.stderr
    assert calls == ""


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"ISOLATED_CANDIDATE_CONFIRMED": "yes"},
        {"SERVICE": "superteacher-overhaul-staging", "ISOLATED_CANDIDATE_CONFIRMED": "yes"},
        {"SERVICE": "superteacher-overhaul-staging", "REPLICA_PREFIX": "overhaul-staging/commit"},
        {
            "SERVICE": "another-staging-service",
            "REPLICA_PREFIX": "overhaul-staging/commit",
            "ISOLATED_CANDIDATE_CONFIRMED": "yes",
        },
    ],
)
def test_shared_stage_or_incomplete_isolation_without_drain_never_calls_cloud(release, settings):
    result, calls = release("synthetic-commit", **settings)
    assert result.returncode != 0
    assert "requires DRAINED_WRITER_CONFIRMED" in result.stderr
    assert calls == ""


@pytest.mark.parametrize(
    "prefix", ["overhaul-staging/", "overhaul-staging/../superteacher", "overhaul-staging//commit"]
)
def test_isolation_prefix_cannot_alias_shared_storage(release, prefix):
    result, calls = release(
        "synthetic-commit",
        SERVICE="superteacher-overhaul-staging",
        REPLICA_PREFIX=prefix,
        ISOLATED_CANDIDATE_CONFIRMED="yes",
    )
    assert result.returncode != 0
    assert calls == ""


def test_shared_stage_rejects_stale_drain_before_build(release):
    result, calls = release("synthetic-commit", DRAINED_WRITER_CONFIRMED="yes", DRAINED_WRITER_REVISION="different")
    assert result.returncode != 0
    assert "differs from" in result.stderr
    assert "builds submit" not in calls and "run deploy" not in calls


def test_shared_stage_rechecks_drain_after_build_before_deploy(release):
    result, calls = release(
        "synthetic-commit",
        DRAINED_WRITER_CONFIRMED="yes",
        DRAINED_WRITER_REVISION="old",
        CHANGE_WRITER_AFTER_BUILD="1",
    )
    assert result.returncode != 0
    assert "differs from" in result.stderr
    assert "builds submit" in calls and calls.count("json(status)") == 2
    assert "run deploy" not in calls and "update-traffic" not in calls


def test_shared_stage_with_matching_drain_checks_twice_and_never_promotes(release):
    result, calls = release("synthetic-commit", DRAINED_WRITER_CONFIRMED="yes", DRAINED_WRITER_REVISION="old")
    assert result.returncode == 0, result.stderr
    assert calls.count("json(status)") == 2
    assert "run deploy superteacher" in calls
    assert "gs://synthetic-project-superteacher-litestream/superteacher" in calls
    assert "update-traffic" not in calls


def test_promotion_without_observed_drain_never_calls_cloud(release):
    result, calls = release("--promote", "superteacher-candidate")
    assert result.returncode != 0
    assert "requires DRAINED_WRITER_CONFIRMED" in result.stderr
    assert calls == ""


def test_isolated_stage_acknowledgment_cannot_bypass_promotion_drain(release):
    result, calls = release(
        "--promote",
        "superteacher-overhaul-staging-candidate",
        SERVICE="superteacher-overhaul-staging",
        REPLICA_PREFIX="overhaul-staging/commit",
        ISOLATED_CANDIDATE_CONFIRMED="yes",
    )
    assert result.returncode != 0
    assert "requires DRAINED_WRITER_CONFIRMED" in result.stderr
    assert calls == ""


def test_promotion_rejects_stale_drain_evidence(release):
    result, calls = release(
        "--promote",
        "superteacher-candidate",
        DRAINED_WRITER_CONFIRMED="yes",
        DRAINED_WRITER_REVISION="different",
    )
    assert result.returncode != 0
    assert "differs from" in result.stderr
    assert "update-traffic" not in calls


def test_promotion_names_revision_without_automatic_rollback(release):
    result, calls = release(
        "--promote",
        "superteacher-candidate",
        DRAINED_WRITER_CONFIRMED="yes",
        DRAINED_WRITER_REVISION="old",
        PROMOTE_EXIT="1",
    )
    assert result.returncode != 0
    assert "--to-revisions superteacher-candidate=100" in calls
    assert calls.count("update-traffic") == 1
    assert "--to-latest" not in calls


@pytest.mark.parametrize("case", ["mismatch", "missing", "duplicate", "reference", "empty"])
def test_promotion_requires_one_literal_matching_candidate_replica(release, case):
    result, calls = release(
        "--promote",
        "superteacher-candidate",
        DRAINED_WRITER_CONFIRMED="yes",
        DRAINED_WRITER_REVISION="old",
        CANDIDATE_ENV_CASE=case,
    )
    assert result.returncode != 0
    assert "exactly one literal replica URL" in result.stderr
    assert "json(spec.containers)" in calls
    assert "update-traffic" not in calls
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert "gs://" not in result.stdout + result.stderr


def test_promotion_with_matching_candidate_replica_moves_only_named_revision(release):
    result, calls = release(
        "--promote",
        "superteacher-candidate",
        DRAINED_WRITER_CONFIRMED="yes",
        DRAINED_WRITER_REVISION="old",
    )
    assert result.returncode == 0, result.stderr
    assert calls.index("json(spec.containers)") < calls.index("update-traffic")
    assert "--to-revisions superteacher-candidate=100" in calls
    assert calls.count("update-traffic") == 1
    assert "gs://" not in result.stdout + result.stderr


def test_verified_restore_marker_is_only_exported_after_restore(tmp_path):
    fake = tmp_path / "litestream"
    fake.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        'restore) exit "${RESTORE_EXIT:-0}" ;;\n'
        'replicate) echo "verified=${LITESTREAM_RESTORE_VERIFIED:-unset}" ;;\nesac\n'
    )
    fake.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "LITESTREAM_REPLICA_URL": "gs://synthetic/replica",
        "DATABASE_URL": "sqlite:////data/synthetic.db",
        "LITESTREAM_RESTORE_VERIFIED": "forged",
    }
    command = ["sh", str(ROOT / "docker-entrypoint.sh"), "true"]
    success = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15, check=False)
    assert success.returncode == 0 and "verified=1" in success.stdout
    failure = subprocess.run(
        command,
        env={**env, "RESTORE_EXIT": "1"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert failure.returncode != 0 and "verified=" not in failure.stdout
