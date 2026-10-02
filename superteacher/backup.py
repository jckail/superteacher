"""Create a validated, private SQLite snapshot without replacing any file."""

import argparse
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path


class BackupError(RuntimeError):
    """An operator-safe message that contains no database contents."""


def _validate(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BackupError("Database integrity validation failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise BackupError("Database foreign key validation failed.")


def backup_database(source: str | Path, destination: str | Path) -> Path:
    """Online backup to a new file; also supports recovery to a fresh location.

    The source is opened in read-only mode. A sibling temporary file is validated
    before an atomic hard-link publishes it, so even a competing destination
    creation cannot cause an overwrite. Parent directories must already exist.
    """
    temporary: Path | None = None
    try:
        source_path = Path(source).resolve(strict=True)
        destination_path = Path(destination).absolute()
        if not source_path.is_file():
            raise BackupError("Source must be an existing SQLite database file.")
        if destination_path.resolve() == source_path or os.path.lexists(destination_path):
            raise BackupError("Destination must be a new file and must not alias the source.")
        if not destination_path.parent.is_dir():
            raise BackupError("Destination parent directory must already exist.")
        # SQLite accepts a zero-byte file as a new database. Reject it here:
        # backups should never silently succeed for an uninitialized source.
        with source_path.open("rb") as source_file:
            if source_file.read(16) != b"SQLite format 3\x00":
                raise BackupError("Source is not an initialized SQLite database.")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".superteacher-backup-", dir=destination_path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

        with (
            closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source_connection,
            closing(sqlite3.connect(temporary)) as snapshot,
        ):
            source_connection.backup(snapshot, pages=128)
            # Produce a standalone database even when the live source uses WAL.
            snapshot.execute("PRAGMA journal_mode=DELETE")
            _validate(snapshot)

        with temporary.open("rb") as snapshot_file:
            os.fsync(snapshot_file.fileno())
        # os.replace/rename can overwrite an existing destination. link cannot.
        os.link(temporary, destination_path)
        return destination_path
    except BackupError:
        raise
    except FileNotFoundError:
        raise BackupError("Source or destination parent does not exist.") from None
    except FileExistsError:
        raise BackupError("Destination already exists; no file was replaced.") from None
    except sqlite3.Error:
        raise BackupError("SQLite backup or validation failed.") from None
    except OSError:
        raise BackupError("Backup filesystem operation failed; check paths and permissions.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
            for suffix in ("-journal", "-wal", "-shm"):
                Path(str(temporary) + suffix).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a validated SQLite backup or restore into a new file.")
    parser.add_argument("source", help="Existing SQLite database or snapshot")
    parser.add_argument("destination", help="New file in an existing directory")
    arguments = parser.parse_args(argv)
    try:
        backup_database(arguments.source, arguments.destination)
    except BackupError as error:
        print(f"Backup failed: {error}", file=sys.stderr)
        return 1
    print("Backup created and validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
