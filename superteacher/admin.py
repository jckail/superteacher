"""Local account operations: explicit existing SQLite file, no app startup or migrations.

Run ``python -m superteacher.admin --help``. Filesystem access is the authority;
the supplied actor ID is an operator assertion, not an authenticated identity.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import stat
import sys
import uuid
from contextlib import closing, suppress
from datetime import UTC, date, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent
# Avoid importing models/db: those initialise the app's configured database.
PASSCODE_OWNER_ID = "owner0000000"
MUTATIONS = {"disable", "enable", "sign-out"}
REQUIRED_COLUMNS = {
    "users": {"id", "email", "disabled", "created_at", "last_login_at"},
    "sessions": {"id_hash", "user_id"},
    "login_tokens": {"token_hash", "email", "consumed_at"},
    "usage_counters": {"user_id", "day", "kind", "count"},
}


class AdminError(Exception):
    """Fixed actionable errors, without database exception text or account PII."""


class AuditIncomplete(AdminError):
    """Mutation committed; the second audit record could not be persisted."""


def _validate_database(conn: sqlite3.Connection) -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    heads = set(ScriptDirectory.from_config(cfg).get_heads())
    try:
        current = {row[0] for row in conn.execute("SELECT version_num FROM alembic_version")}
        if current != heads:
            raise AdminError("Database is not at this checkout's native migration head; no migration was attempted.")
        for table, required in REQUIRED_COLUMNS.items():
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise AdminError("Database account schema is incomplete; no changes were made.")
    except sqlite3.DatabaseError as exc:
        raise AdminError("Database is not a qualified native account database; no changes were made.") from exc


def _open_database(path: Path, *, writable: bool) -> tuple[Path, sqlite3.Connection]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise AdminError("Database must be an existing regular SQLite file.")
        mode = "rw" if writable else "ro"
        conn = sqlite3.connect(f"{resolved.as_uri()}?mode={mode}", uri=True, timeout=5, isolation_level=None)
    except (OSError, sqlite3.Error) as exc:
        raise AdminError("Cannot open the existing database; no file was created.") from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _validate_database(conn)
    except Exception:
        conn.close()
        raise
    return resolved, conn


class AuditLog:
    """Private JSONL intent/outcome records, fsynced and serialised between CLI writers."""

    def __init__(self, path: Path, database: Path):
        self.fd = -1
        try:
            resolved = path.resolve()
            sidecars = {Path(str(database) + suffix) for suffix in ("-wal", "-shm", "-journal")}
            if resolved in {database, *sidecars}:
                raise AdminError("Audit log must be separate from the database and SQLite sidecars.")
            self.fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            info = os.fstat(self.fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or (info.st_dev, info.st_ino) == (database.stat().st_dev, database.stat().st_ino)
            ):
                raise AdminError("Audit log must be an operator-owned regular file with mode 0600 and one link.")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if info.st_size and os.pread(self.fd, 1, info.st_size - 1) != b"\n":
                raise AdminError("Audit log has an incomplete record; reconcile it before another mutation.")
            # Persist a newly created directory entry before allowing a DB commit.
            parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except (OSError, AdminError) as exc:
            self.close()
            if isinstance(exc, AdminError):
                raise
            raise AdminError("Cannot securely open or lock audit log; no changes were made.") from exc

    def append(self, record: dict) -> None:
        data = (json.dumps({**record, "at": datetime.now(UTC).isoformat()}, sort_keys=True) + "\n").encode()
        while data:
            written = os.write(self.fd, data)
            if not written:
                raise OSError("Audit write failed")
            data = data[written:]
        os.fsync(self.fd)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def _user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    if user_id == PASSCODE_OWNER_ID:
        raise AdminError("The implicit passcode owner is outside account administration.")
    row = conn.execute("SELECT id,email,disabled FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AdminError("Account ID was not found; no changes were made.")
    return row


def _mutate(conn: sqlite3.Connection, database: Path, args: argparse.Namespace) -> dict:
    # Reserve the SQLite writer before checking identity and reading current state.
    conn.execute("BEGIN IMMEDIATE")
    audit = None
    intent = False
    committed = False
    record = {"event_id": uuid.uuid4().hex, "actor_id": args.actor, "user_id": args.user_id, "action": args.action}
    try:
        _validate_database(conn)
        user = _user(conn, args.user_id)
        audit = AuditLog(args.audit, database)
        audit.append({**record, "phase": "intent"})
        intent = True
        sessions = links = 0
        if args.action in {"disable", "sign-out"}:
            sessions = conn.execute("DELETE FROM sessions WHERE user_id=?", (args.user_id,)).rowcount
            # Outstanding email links must not silently restore a revoked browser session.
            links = conn.execute(
                "DELETE FROM login_tokens WHERE email=? AND consumed_at IS NULL", (user["email"],)
            ).rowcount
        if args.action in {"disable", "enable"}:
            conn.execute("UPDATE users SET disabled=? WHERE id=?", (args.action == "disable", args.user_id))
        conn.commit()
        committed = True
        result = {"sessions_revoked": sessions, "pending_links_revoked": links}
        try:
            audit.append({**record, "phase": "committed", **result})
        except OSError as exc:
            raise AuditIncomplete(
                f"Mutation COMMITTED; audit outcome incomplete for event {record['event_id']}. "
                "Inspect account state and reconcile the intent record before any retry."
            ) from exc
        return {**record, **result, "committed": True}
    except Exception:
        if not committed:
            conn.rollback()
            if intent and audit is not None:
                # The durable intent remains if rollback logging fails.
                with suppress(OSError):
                    audit.append({**record, "phase": "rolled_back"})
        raise
    finally:
        if audit is not None:
            audit.close()


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", value):
        raise argparse.ArgumentTypeError("Use an ID of 1-64 ASCII letters/digits or _ . : -; no email or free text.")
    return value


def _day(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return value
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Day must be YYYY-MM-DD (UTC).") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="Existing native-head SQLite file; no env default")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="List account IDs, email addresses, state and timestamps (private output)")
    usage = commands.add_parser("usage", help="Inspect used counts only; limits come from runtime configuration")
    usage.add_argument("user_id", type=_identifier)
    usage.add_argument("--day", type=_day, default=datetime.now(UTC).date().isoformat())
    for action in sorted(MUTATIONS):
        command = commands.add_parser(action)
        command.add_argument("user_id", type=_identifier)
        command.add_argument("--actor", required=True, type=_identifier, help="Asserted operator ID; not an email")
        command.add_argument("--audit", required=True, type=Path, help="Private 0600 JSONL file in protected directory")
    args = parser.parse_args(argv)
    try:
        database, conn = _open_database(args.database, writable=args.action in MUTATIONS)
        with closing(conn):
            if args.action == "list":
                users = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id,email,disabled,created_at,last_login_at FROM users WHERE id != ? ORDER BY id",
                        (PASSCODE_OWNER_ID,),
                    )
                ]
                for user in users:
                    user["disabled"] = bool(user["disabled"])
                result = {"users": users}
            elif args.action == "usage":
                _user(conn, args.user_id)
                used = {"chat": 0, "insight": 0, "parent_update": 0}
                used.update(
                    dict(
                        conn.execute(
                            "SELECT kind,count FROM usage_counters WHERE user_id=? AND day=?", (args.user_id, args.day)
                        ).fetchall()
                    )
                )
                result = {"user_id": args.user_id, "day": args.day, "used": used}
            else:
                result = _mutate(conn, database, args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except AuditIncomplete as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except AdminError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        print("Operation failed; inspect account state and audit intent/outcome before retrying.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
