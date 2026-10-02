"""Offline release checks: staging cannot invoke/promote the production writer."""

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
        '  *"json(status)"*) printf \'{"status":{"traffic":[{"percent":100,"revisionName":"old"}]}}\\n\' ;;\n'
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
        "RUNTIME_SERVICE_ACCOUNT": "synthetic@example.iam.gserviceaccount.com",
        "RELEASE_LOG": str(log),
    }
    env.pop("DRAINED_WRITER_CONFIRMED", None)
    env.pop("DRAINED_WRITER_REVISION", None)

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


def test_stage_disables_invocation_and_never_promotes(release):
    result, calls = release("synthetic-commit")
    assert result.returncode == 0, result.stderr
    assert "--no-traffic --no-deploy-health-check" in calls
    assert "--min-instances 0 --min 0" in calls
    assert "FORWARDED_ALLOW_IPS=*" in calls
    assert "gs://synthetic-project-superteacher-litestream/superteacher" in calls
    assert "update-traffic" not in calls and "--to-latest" not in calls


def test_promotion_without_observed_drain_never_calls_cloud(release):
    result, calls = release("--promote", "superteacher-candidate")
    assert result.returncode != 0
    assert "Promotion requires" in result.stderr
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
