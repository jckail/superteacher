"""Explicit offline adoption of published accounts 0002 into native combined 0003.

The input must be a read-only snapshot, not a running application's database.
Only a private clone is migrated. Its exact schema and every preserved row are
verified before a new destination is atomically published; input is never changed.
"""

import argparse
import hashlib
import os
import pickle
import re
import runpy
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL

from .backup import BackupError, _validate, backup_database
from .db import ROOT


class AdoptionError(RuntimeError):
    """Operator-safe failure without record values or SQL exception details."""


def _apply(connection, path):
    migration = runpy.run_path(str(path))
    with Operations.context(MigrationContext.configure(connection)):
        migration["upgrade"]()


def _schema(connection):
    inspector = inspect(connection)
    tables = {}
    for table in sorted(inspector.get_table_names()):
        tables[table] = {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"], c["default"]) for c in inspector.get_columns(table)
            ),
            "primary_key": inspector.get_pk_constraint(table)["constrained_columns"],
            "foreign_keys": sorted(
                (
                    tuple(f["constrained_columns"]),
                    f["referred_table"],
                    tuple(f["referred_columns"]),
                    f["options"].get("ondelete"),
                    f["options"].get("onupdate"),
                )
                for f in inspector.get_foreign_keys(table)
            ),
            "unique": sorted(tuple(c["column_names"]) for c in inspector.get_unique_constraints(table)),
            "checks": sorted((c["name"], c["sqltext"]) for c in inspector.get_check_constraints(table)),
        }
    # SQLAlchemy cannot reflect SQLite functional indexes. Compare their exact
    # normalized definitions, along with any unexpected views or triggers.
    objects = sorted(
        (kind, name, re.sub(r"\s+", " ", sql).strip().lower())
        for kind, name, sql in connection.exec_driver_sql(
            "SELECT type, name, sql FROM sqlite_master WHERE type IN ('index','view','trigger') AND sql IS NOT NULL"
        )
    )
    return tables, objects


def _rows_digest(path):
    digests = {}
    with closing(sqlite3.connect(path)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            if table == "alembic_version":
                continue
            quoted = '"' + table.replace('"', '""') + '"'
            columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
            order = ",".join(str(i + 1) for i in range(len(columns)))
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(f"SELECT * FROM {quoted} ORDER BY {order}"):
                encoded = pickle.dumps(row, protocol=4)
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
                count += 1
            digests[table] = count, digest.digest()
    return digests


def _expected_schemas():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            _apply(connection, ROOT / "alembic/versions/0001_initial_schema.py")
            _apply(connection, ROOT / "superteacher/legacy_accounts_0002.py")
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
            legacy = _schema(connection)
            _apply(connection, ROOT / "alembic/versions/0002_data_integrity.py")
            combined = _schema(connection)
    finally:
        engine.dispose()
    # Independently reconstruct the native lineage. The adoption must produce
    # its actual head schema, not merely agree with its own transformation.
    native_engine = create_engine("sqlite://")
    try:
        with native_engine.begin() as connection:
            for filename in ("0001_initial_schema.py", "0002_data_integrity.py", "0003_accounts.py"):
                _apply(connection, ROOT / "alembic/versions" / filename)
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
            if _schema(connection) != combined:
                raise AdoptionError("Published accounts adoption does not match the native migration chain.")
        return legacy, combined
    finally:
        native_engine.dispose()


def adopt_accounts_snapshot(source, destination):
    """Adopt an explicitly prepared read-only snapshot into a new private file."""
    try:
        source = Path(source).resolve(strict=True)
        destination = Path(destination).absolute()
        if stat.S_IMODE(source.stat().st_mode) & 0o222:
            raise AdoptionError("Input must be a read-only offline snapshot; remove write permissions on the backup.")
        if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise AdoptionError("Input has SQLite sidecars; prepare a standalone offline backup first.")
        if os.path.lexists(destination) or destination.resolve() == source:
            raise AdoptionError("Destination must be a new file and must not alias the input snapshot.")
        if not destination.parent.is_dir():
            raise AdoptionError("Destination parent directory must already exist.")
        legacy, combined = _expected_schemas()
        with tempfile.TemporaryDirectory(prefix=".superteacher-adopt-", dir=destination.parent) as directory:
            os.chmod(directory, 0o700)
            clone = Path(directory) / "clone.db"
            backup_database(source, clone)
            before = _rows_digest(clone)
            engine = create_engine(URL.create("sqlite", database=str(clone)))
            try:
                with engine.connect() as connection:
                    if _schema(connection) != legacy:
                        raise AdoptionError("Snapshot schema does not exactly match published accounts 0002.")
                    if connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() != [("0002",)]:
                        raise AdoptionError("Snapshot must contain exactly the published accounts revision 0002.")
                    connection.commit()
                    with connection.begin():
                        _apply(connection, ROOT / "alembic/versions/0002_data_integrity.py")
                        if _schema(connection) != combined:
                            raise AdoptionError("Migrated clone does not match combined accounts/integrity schema.")
                        # This is the explicit mapping, after applying the missing
                        # native migration and proving the combined schema.
                        connection.exec_driver_sql("UPDATE alembic_version SET version_num='0003'")
                if _rows_digest(clone) != before:
                    raise AdoptionError("Adoption changed preserved records; refusing to publish the clone.")
                with closing(sqlite3.connect(clone)) as connection:
                    _validate(connection)
                return backup_database(clone, destination)
            finally:
                engine.dispose()
    except (AdoptionError, BackupError):
        raise
    except FileNotFoundError:
        raise AdoptionError("Snapshot or destination parent does not exist.") from None
    except Exception:
        raise AdoptionError(
            "Snapshot adoption failed schema, data, or integrity validation; no output was published."
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Read-only standalone offline accounts 0002 snapshot")
    parser.add_argument("destination", help="New adopted SQLite file in an existing private directory")
    args = parser.parse_args(argv)
    try:
        adopt_accounts_snapshot(args.source, args.destination)
    except (AdoptionError, BackupError) as error:
        print(f"Adoption failed: {error}", file=sys.stderr)
        return 1
    print("Accounts snapshot adopted; all records preserved and integrity validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
