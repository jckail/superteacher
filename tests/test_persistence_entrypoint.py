"""docker-entrypoint.sh: restore-on-boot that fails closed, then run the app under Litestream.

Two layers: (1) the shell logic against a fake `litestream` that records its arguments (always runs), and (2) a real
round trip with the actual Litestream binary against a local file replica (runs when LITESTREAM_BIN or `litestream`
on PATH is available; CI installs the pinned release). Neither needs network or GCS.
"""

import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = ROOT / "docker-entrypoint.sh"
CONFIG = ROOT / "litestream.yml"
REAL = os.environ.get("LITESTREAM_BIN") or shutil.which("litestream")

FAKE = """#!/bin/sh
echo "$@" >> "$FAKE_LOG"
case "$1" in
  restore) exit "${FAKE_RESTORE_EXIT:-0}" ;;
  replicate) echo "DB_FILE=$DB_FILE" >> "$FAKE_LOG"; exit 0 ;;
esac
"""


def run(args, env, cwd=None):
    return subprocess.run(
        ["sh", str(ENTRYPOINT), *args], env=env, cwd=cwd, capture_output=True, text=True, timeout=60, check=False
    )


@pytest.fixture
def fake(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "litestream"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    base = {"PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_LOG": str(log), "LITESTREAM_CONFIG": "/cfg.yml"}
    return base, log


def calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_without_a_replica_url_it_just_runs_the_command(fake):
    env, log = fake
    out = run(["echo", "hello"], env)
    assert out.returncode == 0
    assert "hello" in out.stdout and "litestream_disabled" in out.stdout
    assert calls(log) == []  # Litestream was never invoked


def test_restores_then_replicates_with_the_app_as_exec(fake):
    env, log = fake
    env |= {"LITESTREAM_REPLICA_URL": "gcs://b/p", "DATABASE_URL": "sqlite:////data/superteacher.db"}
    out = run(["python", "server.py"], env)
    assert out.returncode == 0, out.stderr
    assert calls(log) == [
        "restore -config /cfg.yml -if-db-not-exists -if-replica-exists /data/superteacher.db",
        "replicate -config /cfg.yml -exec python server.py",
        "DB_FILE=/data/superteacher.db",
    ]


def test_restore_failure_fails_closed_and_never_starts_the_app(fake):
    env, log = fake
    env |= {"LITESTREAM_REPLICA_URL": "gcs://b/p", "DATABASE_URL": "sqlite:////data/x.db", "FAKE_RESTORE_EXIT": "1"}
    out = run(["python", "server.py"], env)
    assert out.returncode == 1
    assert "litestream_restore_failed" in out.stdout
    assert not any(line.startswith("replicate") for line in calls(log))


@pytest.mark.parametrize("url", ["", "sqlite:///relative.db", "sqlite://", "postgresql://u:p@h/db"])
def test_replication_requires_an_absolute_sqlite_path(fake, url):
    env, log = fake
    env |= {"LITESTREAM_REPLICA_URL": "gcs://b/p", "DATABASE_URL": url}
    out = run(["true"], env)
    assert out.returncode == 78 and "litestream_config" in out.stdout
    assert calls(log) == []


# ── real Litestream, file replica ────────────────────────────────────────────────────────────────────────────────
real = pytest.mark.skipif(not REAL, reason="litestream binary not available (set LITESTREAM_BIN)")


def _env(tmp_path, replica):
    bindir = tmp_path / "realbin"
    bindir.mkdir(exist_ok=True)
    link = bindir / "litestream"
    if not link.exists():
        link.symlink_to(REAL)
    return {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "LITESTREAM_CONFIG": str(CONFIG),
        "LITESTREAM_REPLICA_URL": f"file://{replica}",
        "DATABASE_URL": f"sqlite:///{tmp_path}/data/app.db",
    }


WRITE = (
    "import sqlite3,sys,time;c=sqlite3.connect(sys.argv[1]);c.execute('pragma journal_mode=wal');"
    "c.execute('create table if not exists t(x)');c.execute(\"insert into t values('survives')\");c.commit();c.close();"
    "time.sleep(2.5)"  # let Litestream's 1s sync interval run before the app exits
)
READ = "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select x from t').fetchall())"


@real
def test_data_survives_losing_the_disk(tmp_path):
    """Write under replication, delete the local database (a new Cloud Run instance), boot again: the row is back."""
    replica = tmp_path / "replica"
    env = _env(tmp_path, replica)
    db = tmp_path / "data" / "app.db"
    db.parent.mkdir()

    first = run([sys.executable, "-c", WRITE, str(db)], env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert replica.exists() and any(replica.rglob("*")), "nothing was replicated"

    for f in db.parent.glob("*"):  # lose everything local, including litestream's own metadata
        shutil.rmtree(f) if f.is_dir() else f.unlink()

    second = run([sys.executable, "-c", READ, str(db)], env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "[('survives',)]" in second.stdout


@real
def test_first_boot_with_no_replica_starts_empty_without_error(tmp_path):
    env = _env(tmp_path, tmp_path / "empty-replica")
    (tmp_path / "data").mkdir()
    out = run([sys.executable, "-c", "print('app-ran')"], env)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "app-ran" in out.stdout


@real
def test_unusable_replica_fails_closed(tmp_path):
    """A replica that exists but cannot be read must stop the boot, not start an empty database."""
    blocker = tmp_path / "replica-is-a-file"
    blocker.write_text("not a directory")
    env = _env(tmp_path, blocker)
    (tmp_path / "data").mkdir()
    out = run([sys.executable, "-c", "print('app-ran')"], env)
    assert out.returncode != 0
    assert "app-ran" not in out.stdout


def test_app_enables_wal_on_file_databases(tmp_path):
    from superteacher import db as database

    eng = database.make_engine(f"sqlite:///{tmp_path}/x.db")
    with eng.connect() as conn:
        assert conn.exec_driver_sql("pragma journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("pragma foreign_keys").scalar() == 1
    mem = database.make_engine("sqlite://")
    with mem.connect() as conn:
        assert conn.exec_driver_sql("pragma journal_mode").scalar() == "memory"
    assert sqlite3  # (module import used by WRITE/READ strings above)


def test_arguments_with_spaces_and_quotes_are_requoted_for_litestream_exec(fake):
    env, log = fake
    env |= {"LITESTREAM_REPLICA_URL": "gcs://b/p", "DATABASE_URL": "sqlite:////data/x.db"}
    run(["python", "-c", "print('it''s here')", "two words", ""], env)
    exec_line = next(line for line in calls(log) if line.startswith("replicate"))
    assert (
        exec_line == "replicate -config /cfg.yml -exec python -c 'print('\\''it'\\'''\\''s here'\\'')' 'two words' ''"
    )
