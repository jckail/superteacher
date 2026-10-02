import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from superteacher.config import Settings
from superteacher.main import create_app


def test_cloud_run_refuses_ephemeral_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("K_SERVICE", "synthetic-review-service")
    path = tmp_path / "ephemeral.db"
    engine = create_engine(f"sqlite:///{path}")
    try:
        with pytest.raises(RuntimeError, match="durable server database"):
            create_app(engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True))
        assert not path.exists()
    finally:
        engine.dispose()


def test_local_persistent_sqlite_remains_supported(monkeypatch, tmp_path):
    monkeypatch.delenv("K_SERVICE", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'local.db'}")
    try:
        app = create_app(
            engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True)
        )
        assert app.state.session_factory.kw["bind"] is engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "verified, replica, matching",
    [
        ("", "gs://synthetic/replica", True),
        ("1", "gcs://synthetic/replica", True),
        ("1", "gs://synthetic/replica", False),
    ],
)
def test_cloud_run_replica_configuration_alone_is_not_enough(monkeypatch, tmp_path, verified, replica, matching):
    monkeypatch.setenv("K_SERVICE", "synthetic-review-service")
    path = tmp_path / "replicated.db"
    monkeypatch.setenv("DB_FILE", str(path if matching else tmp_path / "other.db"))
    monkeypatch.setenv("LITESTREAM_RESTORE_VERIFIED", verified)
    monkeypatch.setenv("LITESTREAM_REPLICA_URL", replica)
    engine = create_engine(f"sqlite:///{path}")
    try:
        with pytest.raises(RuntimeError, match="verified Litestream restore"):
            create_app(engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True))
        assert not path.exists()
    finally:
        engine.dispose()


def test_cloud_run_accepts_entrypoint_verified_replica(monkeypatch, tmp_path):
    monkeypatch.setenv("K_SERVICE", "synthetic-review-service")
    path = tmp_path / "replicated.db"
    monkeypatch.setenv("DB_FILE", str(path))
    monkeypatch.setenv("LITESTREAM_RESTORE_VERIFIED", "1")
    monkeypatch.setenv("LITESTREAM_REPLICA_URL", "gs://synthetic/replica")
    engine = create_engine(f"sqlite:///{path}")
    try:
        app = create_app(
            engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True)
        )
        assert app.state.session_factory.kw["bind"] is engine
    finally:
        engine.dispose()


def test_runtime_root_files_are_readable_after_owner_only_archive_copy(tmp_path):
    root = Path(__file__).resolve().parents[1]
    names = ("alembic.ini", "server.py", "litestream.yml", "docker-entrypoint.sh")
    copied = {}
    for name in names:
        target = tmp_path / name
        shutil.copyfile(root / name, target)
        target.chmod(0o600)
        copied[f"/app/{name}"] = target

    # Exercise the Dockerfile's actual permission operations before its non-root
    # USER boundary, starting with the modes retained by a private release archive.
    dockerfile = (root / "Dockerfile").read_text().split("USER app", 1)[0]
    for line in dockerfile.splitlines():
        if not line.startswith("RUN chmod "):
            continue
        command = shlex.split(line.removeprefix("RUN "))
        if not all(path in copied for path in command[2:]):
            continue
        subprocess.run([*command[:2], *(str(copied[path]) for path in command[2:])], check=True)

    for target in copied.values():
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode & stat.S_IROTH, f"runtime UID 10001 cannot read {target.name}"
        assert not mode & stat.S_IWOTH, f"runtime file is writable by other users: {target.name}"
    assert stat.S_IMODE(copied["/app/docker-entrypoint.sh"].stat().st_mode) & stat.S_IXOTH
