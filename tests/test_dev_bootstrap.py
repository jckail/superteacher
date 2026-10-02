"""Dependency-free bootstrap checks; never install packages or start app servers."""

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("dev_bootstrap", Path(__file__).parents[1] / "scripts/dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    for name in ("requirements.lock", "web/package-lock.json", "web/package.json"):
        (tmp_path / name).write_text("{}")
    state = tmp_path / ".superteacher-dev"
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "STATE", state)
    monkeypatch.setattr(dev, "PYTHON", state / "venv/bin/python")
    monkeypatch.setattr(dev, "STAMP", state / "installed.json")
    previous_umask = os.umask(0o077)
    try:
        yield tmp_path
    finally:
        os.umask(previous_umask)


def test_install_uses_python312_hashes_and_locked_npm(checkout, monkeypatch):
    run = Mock()
    monkeypatch.setattr(dev.subprocess, "run", run)
    dev.install()
    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0][:4] == ["uv", "venv", "--python", "3.12"]
    assert commands[1] == ["uv", "pip", "sync", "--python", str(dev.PYTHON), "--require-hashes", "requirements.lock"]
    assert commands[2] == ["npm", "ci"]
    assert json.loads(dev.STAMP.read_text()) == dev.fingerprint()


@pytest.mark.parametrize("path", ["web/node_modules", ".superteacher-dev"])
def test_preserves_unowned_dependencies(checkout, monkeypatch, path):
    owned = checkout / path
    owned.mkdir()
    (owned / "keep").write_text("preserve")
    run = Mock()
    monkeypatch.setattr(dev.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="preserve"):
        dev.install()
    run.assert_not_called()
    assert (owned / "keep").read_text() == "preserve"


def test_shared_node_modules_never_replaced(checkout, monkeypatch, tmp_path):
    dev.STATE.mkdir()
    dev.STAMP.write_text("{}")
    target = tmp_path / "shared"
    target.mkdir()
    (checkout / "web/node_modules").symlink_to(target)
    run = Mock()
    monkeypatch.setattr(dev.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="symlink"):
        dev.install()
    run.assert_not_called()
    assert (checkout / "web/node_modules").is_symlink()


def test_lock_drift_and_missing_runtime_require_setup(checkout):
    dev.PYTHON.parent.mkdir(parents=True)
    dev.PYTHON.touch()
    vite = checkout / "web/node_modules/.bin/vite"
    vite.parent.mkdir(parents=True)
    vite.touch()
    dev.STAMP.write_text(json.dumps(dev.fingerprint()))
    assert dev.ready()
    (checkout / "requirements.lock").write_text("changed")
    assert not dev.ready()
    dev.STAMP.write_text(json.dumps(dev.fingerprint()))
    dev.PYTHON.unlink()
    assert not dev.ready()


def test_demo_overrides_real_data_credentials(checkout, monkeypatch):
    for name in ("DATABASE_URL", "ANTHROPIC_API_KEY", "SENDGRID_API_KEY", "SESSION_SECRET", "K_SERVICE"):
        monkeypatch.setenv(name, "production-sentinel")
    env = dev.local_environment()
    assert env["DATABASE_URL"] == f"sqlite:///{dev.STATE / 'demo.db'}"
    assert env["SEED_DEMO_DATA"] == "true"
    assert env["AUTH_DISABLED"] == "true"
    assert env["AUTH_MODE"] == "passcode"
    for name in ("ANTHROPIC_API_KEY", "SENDGRID_API_KEY", "SESSION_SECRET", "K_SERVICE"):
        assert env[name] == ""


@pytest.mark.parametrize("version", ["v20.19.0", "v22.11.0"])
def test_rejects_unsupported_node(monkeypatch, version):
    monkeypatch.setattr(dev.shutil, "which", lambda tool: tool)
    monkeypatch.setattr(dev.subprocess, "check_output", lambda *a, **k: version)
    with pytest.raises(RuntimeError, match=r"22\.12"):
        dev.preflight()


def test_occupied_port_rejected_without_touching_owner(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda tool: tool)
    monkeypatch.setattr(dev.subprocess, "check_output", lambda *a, **k: "v22.12.0")
    with socket.socket() as owner:
        try:
            owner.bind(("127.0.0.1", 8080))
        except OSError:
            pytest.skip("8080 already belongs to another server")
        with pytest.raises(RuntimeError, match="8080 is occupied"):
            dev.preflight()
        assert owner.getsockname()[1] == 8080


def test_cleanup_kills_only_owned_groups():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    unrelated = subprocess.Popen(command, start_new_session=True)
    owned = subprocess.Popen(command, start_new_session=True)
    try:
        dev.stop([owned])
        assert owned.poll() is not None
        assert unrelated.poll() is None
        assert os.getpgid(unrelated.pid) == unrelated.pid
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
        if owned.poll() is None:
            owned.kill()
            owned.wait(timeout=5)


def test_second_server_spawn_failure_stops_first(monkeypatch):
    child = Mock(pid=987654)
    popen = Mock(side_effect=[child, OSError("spawn failed")])
    stop = Mock()
    monkeypatch.setattr(dev.subprocess, "Popen", popen)
    monkeypatch.setattr(dev, "stop", stop)
    with pytest.raises(OSError, match="spawn failed"):
        dev.serve()
    stop.assert_called_once_with([child])
    assert popen.call_args_list[0].kwargs["start_new_session"] is True
    assert "127.0.0.1" in popen.call_args_list[0].args[0]
    assert "--strictPort" in popen.call_args_list[1].args[0]


def test_busy_resource_gate_never_starts_servers(checkout, monkeypatch):
    gate = checkout / "fake-gate"
    gate.touch()
    monkeypatch.setattr(dev, "GATE", gate)
    run = Mock(return_value=75)
    serve = Mock()
    monkeypatch.setattr(dev, "ready", lambda: False)
    monkeypatch.setattr(dev, "run_setup", run)
    monkeypatch.setattr(dev, "serve", serve)
    assert dev.managed_run() == 75
    assert run.call_count == 1
    assert run.call_args.args[0][:2] == [str(gate), "--"]
    serve.assert_not_called()
    assert not dev.STATE.exists()


def test_env_overrides_dotenv_using_actual_settings(checkout, monkeypatch):
    from superteacher.config import Settings

    dotenv = checkout / ".env"
    dotenv.write_text(
        "DATABASE_URL=sqlite:////production.db\nANTHROPIC_API_KEY=secret-sentinel\nAUTH_DISABLED=false\nSEED_DEMO_DATA=false\nAUTH_MODE=accounts\n"
    )
    for key, value in dev.local_environment().items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=dotenv)
    assert settings.database_url == f"sqlite:///{dev.STATE / 'demo.db'}"
    assert settings.auth_disabled
    assert settings.seed_demo_data
    assert settings.auth_mode == "passcode"
    assert not settings.anthropic_api_key
    assert not settings.session_secret
    assert "production" not in settings.database_url


def test_managed_run_reuses_matching_locks(checkout, monkeypatch):
    run = Mock()
    serve = Mock(return_value=0)
    monkeypatch.setattr(dev, "ready", lambda: True)
    monkeypatch.setattr(dev, "preflight", Mock())
    monkeypatch.setattr(dev.subprocess, "run", run)
    monkeypatch.setattr(dev, "serve", serve)
    assert dev.managed_run() == 0
    run.assert_not_called()
    serve.assert_called_once()


def test_check_does_not_install_or_create_state(checkout, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dev.py", "--check"])
    monkeypatch.setattr(dev, "preflight", Mock())
    install = Mock()
    monkeypatch.setattr(dev, "install", install)
    assert dev.main() == 0
    install.assert_not_called()
    assert not dev.STATE.exists()
    assert not (checkout / ".superteacher-dev.lock").exists()


def test_same_worktree_lock_preserves_other_launcher(checkout, monkeypatch):
    import fcntl

    monkeypatch.setattr(sys, "argv", ["dev.py"])
    monkeypatch.setattr(dev, "preflight", Mock())
    managed = Mock()
    monkeypatch.setattr(dev, "managed_run", managed)
    with (checkout / ".superteacher-dev.lock").open("w") as existing:
        fcntl.flock(existing, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert dev.main() == 2
        managed.assert_not_called()


def test_failed_repair_invalidates_previous_success(checkout, monkeypatch):
    dev.PYTHON.parent.mkdir(parents=True)
    dev.PYTHON.touch()
    vite = checkout / "web/node_modules/.bin/vite"
    vite.parent.mkdir(parents=True)
    vite.touch()
    dev.write_stamp(dev.fingerprint())
    assert dev.ready()
    run = Mock(side_effect=subprocess.CalledProcessError(1, ["uv", "pip", "sync"]))
    monkeypatch.setattr(dev.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        dev.install()
    assert not dev.ready()
    assert json.loads(dev.STAMP.read_text()) == {}


def test_interrupted_gate_is_awaited_and_never_force_killed(monkeypatch):
    child = Mock()
    child.wait.side_effect = [KeyboardInterrupt, 130]
    popen = Mock(return_value=child)
    stop = Mock()
    monkeypatch.setattr(dev.subprocess, "Popen", popen)
    monkeypatch.setattr(dev, "stop", stop)
    assert dev.run_setup(["gate", "--", "installer"], gated=True) == 130
    child.send_signal.assert_called_once_with(dev.signal.SIGTERM)
    assert child.wait.call_count == 2
    stop.assert_not_called()
    assert popen.call_args.kwargs["start_new_session"] is True


def test_signal_during_setup_spawn_keeps_child_owned(monkeypatch):
    child = Mock()
    child.wait.return_value = 130

    def spawn(*args, **kwargs):
        dev.signal.getsignal(dev.signal.SIGTERM)(dev.signal.SIGTERM, None)
        return child

    monkeypatch.setattr(dev.subprocess, "Popen", spawn)
    assert dev.run_setup(["gate"], gated=True) == 130
    child.send_signal.assert_called_once_with(dev.signal.SIGTERM)
    child.wait.assert_called_once()


def test_lock_change_during_install_never_publishes_success(checkout, monkeypatch):
    def changed(*args, **kwargs):
        (checkout / "requirements.lock").write_text("changed mid-install")

    monkeypatch.setattr(dev.subprocess, "run", changed)
    with pytest.raises(RuntimeError, match="locks changed"):
        dev.install()
    assert json.loads(dev.STAMP.read_text()) == {}


def test_signal_during_server_spawn_still_cleans_owned_child(monkeypatch):
    child = Mock(pid=987654)

    def spawn(*args, **kwargs):
        dev.signal.getsignal(dev.signal.SIGTERM)(dev.signal.SIGTERM, None)
        return child

    stop = Mock()
    monkeypatch.setattr(dev.subprocess, "Popen", spawn)
    monkeypatch.setattr(dev, "stop", stop)
    assert dev.serve() == 0
    stop.assert_called_once_with([child])


def test_interrupted_venv_is_resumed_without_removing_files(checkout, monkeypatch):
    venv = dev.STATE / "venv"
    venv.mkdir(parents=True)
    marker = venv / "preserve-existing-file"
    marker.write_text("keep")
    dev.write_stamp({})

    def fake_install(command, **kwargs):
        if command[:2] == ["uv", "venv"]:
            # Model uv's documented refusal of an existing target by default.
            if "--allow-existing" not in command:
                raise subprocess.CalledProcessError(2, command)
            dev.PYTHON.parent.mkdir(parents=True, exist_ok=True)
            dev.PYTHON.touch()
        if command == ["npm", "ci"]:
            vite = checkout / "web/node_modules/.bin/vite"
            vite.parent.mkdir(parents=True)
            vite.touch()

    monkeypatch.setattr(dev.subprocess, "run", fake_install)
    dev.install()
    assert marker.read_text() == "keep"
    assert dev.ready()


def test_partial_venv_symlink_is_never_repaired(checkout, monkeypatch):
    dev.STATE.mkdir()
    dev.write_stamp({})
    target = checkout / "shared-venv"
    target.mkdir()
    (target / "keep").write_text("preserve")
    (dev.STATE / "venv").symlink_to(target)
    run = Mock()
    monkeypatch.setattr(dev.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="symlink"):
        dev.install()
    run.assert_not_called()
    assert (target / "keep").read_text() == "preserve"


@pytest.mark.parametrize("name", ["demo.db", "demo.db-wal", "demo.db-shm", "demo.db-journal"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink", "dangling"])
def test_database_alias_refused_before_any_child(checkout, monkeypatch, name, alias):
    dev.STATE.mkdir(mode=0o700)
    sentinel = checkout / "unrelated-records"
    sentinel.write_bytes(b"preserve unrelated records")
    target = dev.STATE / name
    if alias == "hardlink":
        os.link(sentinel, target)
    else:
        target.symlink_to(sentinel if alias == "symlink" else checkout / "absent")
    setup, serve = Mock(), Mock()
    monkeypatch.setattr(dev, "ready", lambda: True)
    monkeypatch.setattr(dev, "preflight", Mock())
    monkeypatch.setattr(dev, "run_setup", setup)
    monkeypatch.setattr(dev, "serve", serve)
    with pytest.raises(RuntimeError, match=r"demo|database"):
        dev.managed_run()
    setup.assert_not_called()
    serve.assert_not_called()
    assert sentinel.read_bytes() == b"preserve unrelated records"
    assert target.is_symlink() if alias != "hardlink" else target.stat().st_nlink == 2


@pytest.mark.parametrize("mode", [0o755, 0o770])
def test_nonprivate_state_refused(checkout, monkeypatch, mode):
    dev.STATE.mkdir(mode=mode)
    dev.STATE.chmod(mode)
    monkeypatch.setattr(dev, "ready", lambda: True)
    monkeypatch.setattr(dev, "preflight", Mock())
    serve = Mock()
    monkeypatch.setattr(dev, "serve", serve)
    with pytest.raises(RuntimeError, match="private"):
        dev.managed_run()
    serve.assert_not_called()


@pytest.mark.parametrize("kind", ["directory", "fifo", "public-file"])
def test_unsafe_database_entry_refused(checkout, monkeypatch, kind):
    dev.STATE.mkdir(mode=0o700)
    target = dev.STATE / "demo.db"
    if kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target, 0o600)
    else:
        target.touch(mode=0o644)
        target.chmod(0o644)
    monkeypatch.setattr(dev, "ready", lambda: True)
    monkeypatch.setattr(dev, "preflight", Mock())
    serve = Mock()
    monkeypatch.setattr(dev, "serve", serve)
    with pytest.raises(RuntimeError, match="database"):
        dev.managed_run()
    serve.assert_not_called()
    assert target.exists()


@pytest.mark.parametrize("existing", [False, True])
def test_private_regular_demo_can_resume_without_opening_database(checkout, monkeypatch, existing):
    dev.STATE.mkdir(mode=0o700)
    if existing:
        for suffix in ("", "-wal", "-shm", "-journal"):
            (dev.STATE / f"demo.db{suffix}").touch(mode=0o600)
    monkeypatch.setattr(dev, "ready", lambda: True)
    monkeypatch.setattr(dev, "preflight", Mock())
    serve = Mock(return_value=0)
    monkeypatch.setattr(dev, "serve", serve)
    assert dev.managed_run() == 0
    serve.assert_called_once()


@pytest.mark.parametrize("other_owner", [False, True])
def test_removed_internal_install_entry_never_runs_install(checkout, monkeypatch, other_owner):
    import fcntl

    monkeypatch.setattr(sys, "argv", ["dev.py", "--install"])
    monkeypatch.setattr(dev, "preflight", Mock())
    install = Mock()
    monkeypatch.setattr(dev, "install", install)
    with (checkout / ".superteacher-dev.lock").open("w") as lock:
        if other_owner:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(SystemExit) as exc:
            dev.main()
        assert exc.value.code == 2
    install.assert_not_called()
    assert not dev.STATE.exists()
