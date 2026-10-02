"""Linux local demo bootstrap; no application imports or credentials required."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".superteacher-dev"
PYTHON = STATE / "venv/bin/python"
STAMP = STATE / "installed.json"
GATE = Path("/home/jkail/.local/bin/agent-heavy-check")


def fingerprint():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("requirements.lock", "web/package-lock.json", "web/package.json")
    }


def qualify_demo_state():
    """Preserve unsafe paths; existing regular data belongs to the trusted operator."""
    try:
        info = STATE.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("Demo state must be an owned private directory; preserve it and use manual setup.")
    for suffix in ("", "-wal", "-shm", "-journal"):
        target = STATE / f"demo.db{suffix}"
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise RuntimeError(f"Unsafe demo database path {target.name}; preserve it and use manual setup.")


def ready():
    try:
        qualify_demo_state()
        if (
            STATE.is_symlink()
            or STAMP.is_symlink()
            or (STATE / "venv").is_symlink()
            or (ROOT / "web/node_modules").is_symlink()
        ):
            return False
        return (
            json.loads(STAMP.read_text()) == fingerprint()
            and PYTHON.is_file()
            and (ROOT / "web/node_modules/.bin/vite").is_file()
        )
    except (OSError, ValueError, RuntimeError):
        return False


def preflight():
    if sys.platform != "linux":
        raise RuntimeError("Use Linux/WSL, or the manual setup in README.md.")
    for tool in ("uv", "node", "npm"):
        if not shutil.which(tool):
            raise RuntimeError(f"Missing {tool}; install it using its official instructions first.")
    version = subprocess.check_output(["node", "--version"], text=True).strip()
    major, minor, *_ = map(int, version.lstrip("v").split("."))
    if major < 22 or (major == 22 and minor < 12):
        raise RuntimeError("Node 22.12+ is required.")
    for port in (8080, 4000):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Port {port} is occupied; preserve its owner and free it explicitly.") from exc


def write_stamp(value):
    with tempfile.NamedTemporaryFile(mode="w", dir=STATE, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, STAMP)
        finally:
            temporary.unlink(missing_ok=True)


def install():
    # Refuse to adopt another setup's dependencies, including symlinks.
    if STATE.is_symlink() or STAMP.is_symlink() or (STATE.exists() and not STAMP.is_file()):
        raise RuntimeError("Unowned .superteacher-dev exists; preserve it and use manual setup.")
    if (ROOT / "web/node_modules").exists() and not STAMP.is_file():
        raise RuntimeError("Existing node_modules has no bootstrap stamp; preserve it and use manual setup.")
    if (ROOT / "web/node_modules").is_symlink():
        raise RuntimeError("Refusing to replace shared node_modules symlink.")
    if (STATE / "venv").is_symlink():
        raise RuntimeError("Refusing to repair a shared virtual environment symlink.")
    qualify_demo_state()
    STATE.mkdir(mode=0o700, exist_ok=True)
    target = fingerprint()
    # Invalidate even a previous successful stamp before any repair mutations.
    write_stamp({})
    if not PYTHON.exists():
        subprocess.run(
            ["uv", "venv", "--python", "3.12", "--allow-existing", str(STATE / "venv")], cwd=ROOT, check=True
        )
    subprocess.run(
        ["uv", "pip", "sync", "--python", str(PYTHON), "--require-hashes", "requirements.lock"], cwd=ROOT, check=True
    )
    subprocess.run(["npm", "ci"], cwd=ROOT / "web", check=True)
    if fingerprint() != target:
        raise RuntimeError("Dependency locks changed during setup; no successful stamp published.")
    write_stamp(target)


def local_environment():
    qualify_demo_state()
    env = os.environ.copy()
    # Environment values override .env, including production data/provider settings.
    env.update(
        DATABASE_URL=f"sqlite:///{STATE / 'demo.db'}",
        AUTH_DISABLED="true",
        AUTH_MODE="passcode",
        AUTH_PASSWORD="",
        SESSION_SECRET="",
        SEED_DEMO_DATA="true",
        ANTHROPIC_API_KEY="",
        SENDGRID_API_KEY="",
        AUTH_EMAIL_BACKEND="console",
        SMTP_PASSWORD="",
        K_SERVICE="",
        CORS_ORIGINS='["http://localhost:4000"]',
        PUBLIC_BASE_URL="http://localhost:4000",
    )
    return env


def stop(children):
    for child in children:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    for child in children:
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    # A supervisor may exit before a descendant; never leave its group behind.
    for child in children:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)


def serve():
    qualify_demo_state()
    children = []
    spawning = False
    pending = False

    def interrupted(_signum, _frame):
        nonlocal pending
        if spawning:
            pending = True
            return
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        commands = [
            (
                [
                    str(PYTHON),
                    "-m",
                    "uvicorn",
                    "superteacher.main:app",
                    "--reload",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8080",
                ],
                ROOT,
            ),
            (["npm", "run", "dev", "--", "--host", "127.0.0.1", "--strictPort"], ROOT / "web"),
        ]
        for command, cwd in commands:
            spawning = True
            try:
                child = subprocess.Popen(command, cwd=cwd, env=local_environment(), start_new_session=True, umask=0o077)
                children.append(child)
            finally:
                spawning = False
            if pending:
                raise KeyboardInterrupt
            print(f"Owned server pid={child.pid} cwd={cwd}; logs stream to this terminal", flush=True)
        print("Synthetic demo: http://localhost:4000 (API 127.0.0.1:8080). Ctrl-C stops both.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.2)
        return next(child.returncode or 1 for child in children if child.returncode is not None)
    except KeyboardInterrupt:
        return 0
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        stop(children)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check tools/ports only; no installs or servers")
    args = parser.parse_args()
    try:
        preflight()
        if args.check:
            print(f"Preflight passed; dependencies {'ready' if ready() else 'need managed setup'}.")
            return 0
        lock_fd = os.open(ROOT / ".superteacher-dev.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock_fd, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another bootstrap owns this worktree; preserve its setup/server.") from exc
            return managed_run()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Local setup stopped: {exc}", file=sys.stderr)
        return 2


def run_setup(command, *, gated):
    # The gate owns its separate payload scope; let it finish cleanup before
    # releasing this worktree lock. Never force-kill the gate supervisor.
    child = None
    spawning = False
    pending = False

    def interrupted(_signum, _frame):
        nonlocal pending
        if spawning:
            pending = True
            return
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        spawning = True
        try:
            child = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
        finally:
            spawning = False
        if pending:
            raise KeyboardInterrupt
        return child.wait()
    except KeyboardInterrupt:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        if child is not None:
            if gated:
                with suppress(ProcessLookupError):
                    child.send_signal(signal.SIGTERM)
                child.wait()
            else:
                stop([child])
        return 130
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def managed_run():
    qualify_demo_state()
    if not ready():
        gate = GATE
        # No standalone install CLI: this payload is constructed only while
        # main holds the worktree lock, and admitted by the shared gate below.
        payload = f"import runpy, sys; sys.exit(runpy.run_path({str(Path(__file__).resolve())!r})['installer_main']())"
        command = [sys.executable, "-c", payload]
        if gate.is_file():
            command.insert(0, "--")
            command.insert(0, str(gate))
        elif os.environ.get("WSL_DISTRO_NAME"):
            raise RuntimeError("WSL resource gate is missing; restore agent-heavy-check before installing.")
        result = run_setup(command, gated=gate.is_file())
        if result:
            return result
    # Recheck before spawning: another process may have claimed a port during setup.
    qualify_demo_state()
    preflight()
    return serve()


def installer_main():
    """Keep the gated child's failure contract consistent with the launcher."""
    try:
        install()
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Local setup stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
