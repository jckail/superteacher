"""Distinguish SQLAlchemy autobegin from SQLite's physical transactions."""

import pytest
from alembic.config import Config
from sqlalchemy import event

from alembic import command
from superteacher import db as database


def migration_config():
    config = Config(str(database.ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(database.ROOT / "alembic"))
    return config


@pytest.fixture
def baseline_file(tmp_path):
    engine = database.make_engine(f"sqlite:///{tmp_path / 'physical-transaction.db'}")
    config = migration_config()
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO courses VALUES ('c', 'Math')")
        connection.exec_driver_sql("INSERT INTO sections VALUES ('sec', 'c', 'A')")
        connection.exec_driver_sql("INSERT INTO students VALUES ('s', 'Synthetic', 8, 'sec')")
        connection.exec_driver_sql("INSERT INTO assessments VALUES ('a', 'sec', 'History', 'quiz', 10, '2026-10-01')")
        connection.exec_driver_sql("INSERT INTO scores VALUES ('score', 'a', 's', 12)")
    yield engine
    engine.dispose()


def preserved_rows(engine):
    with engine.connect() as connection:
        return {
            table: connection.exec_driver_sql(f'SELECT * FROM "{table}" ORDER BY 1').all()
            for table in ("sections", "students", "assessments", "scores")
        }


def test_pragma_autobegin_is_not_a_physical_sqlite_transaction(baseline_file):
    with baseline_file.connect() as connection:
        driver = connection.connection.driver_connection
        assert not connection.in_transaction() and not driver.in_transaction
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.in_transaction() and not driver.in_transaction
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
        assert not driver.in_transaction
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


@pytest.mark.parametrize("entrypoint", ["startup", "provided_connection", "cli_engine"])
def test_real_file_migration_disables_fks_outside_physical_transaction(baseline_file, monkeypatch, entrypoint):
    before = preserved_rows(baseline_file)
    physical_states = []

    @event.listens_for(baseline_file, "before_cursor_execute")
    def observe(connection, cursor, statement, parameters, context, executemany):
        if statement.upper().replace(" ", "") == "PRAGMAFOREIGN_KEYS=OFF":
            physical_states.append(connection.connection.driver_connection.in_transaction)

    if entrypoint == "startup":
        database.run_migrations(baseline_file)
    elif entrypoint == "provided_connection":
        config = migration_config()
        with baseline_file.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    else:
        # No supplied connection: exercise env.py's normal CLI engine path.
        monkeypatch.setattr(database, "make_engine", lambda url: baseline_file)
        command.upgrade(migration_config(), "head")
    assert physical_states and not any(physical_states)
    assert preserved_rows(baseline_file) == before
    with baseline_file.connect() as connection:
        # Normal CLI owns/closes its connection; restore FK before returning a
        # provided connection/startup pool to application code.
        if entrypoint != "cli_engine":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0003"


def test_actual_caller_sqlite_transaction_is_rejected_before_migration(baseline_file):
    before = preserved_rows(baseline_file)
    config = migration_config()
    with baseline_file.connect() as connection:
        connection.exec_driver_sql("UPDATE students SET name='Pending change'")
        assert connection.in_transaction() and connection.connection.driver_connection.in_transaction
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="foreign_keys=OFF before starting a transaction"):
            command.upgrade(config, "head")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001"
        connection.rollback()
    assert preserved_rows(baseline_file) == before
