from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from superteacher import db as database
from superteacher import models  # noqa: F401


def _shape(eng):
    insp = inspect(eng)
    out = {}
    for t in sorted(insp.get_table_names()):
        if t == "alembic_version":
            continue
        out[t] = (
            sorted((c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(t)),
            sorted(
                (tuple(f["constrained_columns"]), f["referred_table"], f["options"].get("ondelete"))
                for f in insp.get_foreign_keys(t)
            ),
            sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(t)),
            sorted(tuple(u["column_names"]) for u in insp.get_unique_constraints(t)),
            tuple(insp.get_pk_constraint(t)["constrained_columns"]),
            sorted((check["name"], check["sqltext"]) for check in insp.get_check_constraints(t)),
        )
    return out


def _baseline(eng):
    cfg = Config(str(database.ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(database.ROOT / "alembic"))
    with eng.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
        conn.execute(text("drop table alembic_version"))
        conn.commit()


def test_migration_matches_metadata(tmp_path):
    migrated = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    database.run_migrations(migrated)
    created = create_engine("sqlite://")
    database.Base.metadata.create_all(created)
    assert _shape(migrated) == _shape(created)
    with migrated.connect() as conn:  # no drift between models and migration head
        assert (
            compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), database.Base.metadata)
            == []
        )
        assert conn.execute(text("select version_num from alembic_version")).scalar() is not None


def test_startup_never_drops_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'keep.db'}"
    eng = create_engine(url)
    database.run_migrations(eng)
    with eng.begin() as c:
        c.execute(text("insert into courses (id, name) values ('c1', 'Math')"))
    database.run_migrations(eng)  # second startup
    with eng.connect() as c:
        assert c.execute(text("select name from courses")).scalar() == "Math"


def test_legacy_db_without_alembic_version_is_stamped_not_recreated(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _baseline(eng)  # how the app created DBs before Alembic
    with eng.begin() as c:
        c.execute(text("insert into courses (id, name) values ('c1', 'Science')"))
    database.run_migrations(eng)
    with eng.connect() as c:
        assert c.execute(text("select name from courses")).scalar() == "Science"
        assert c.execute(text("select count(*) from alembic_version")).scalar() == 1


def test_alembic_files_present():
    root = Path(database.ROOT)
    assert (root / "alembic.ini").is_file() and list((root / "alembic" / "versions").glob("0001_*.py"))


@pytest.mark.parametrize("drift", ["missing_table", "missing_column", "wrong_type", "missing_index"])
def test_partial_or_drifted_legacy_schema_is_not_stamped(tmp_path, drift):
    eng = create_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    try:
        _baseline(eng)
        with eng.begin() as conn:
            conn.execute(text("insert into courses (id, name) values ('c1', 'Keep me')"))
            if drift == "missing_table":
                conn.execute(text("drop table insights"))
            elif drift == "missing_column":
                conn.execute(text("alter table insights drop column model"))
            elif drift == "wrong_type":
                conn.execute(text("drop table insights"))
                conn.execute(text("create table insights (student_id integer primary key)"))
            else:
                conn.execute(text("drop index ix_students_name"))
        before = _shape(eng)
        with pytest.raises(RuntimeError, match="refusing to stamp"):
            database.run_migrations(eng)
        assert _shape(eng) == before
        assert "alembic_version" not in inspect(eng).get_table_names()
        with eng.connect() as conn:
            assert conn.execute(text("select name from courses")).scalar() == "Keep me"
    finally:
        eng.dispose()


def test_supported_legacy_schema_can_coexist_with_unrelated_tables(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'extra.db'}")
    try:
        _baseline(eng)
        with eng.begin() as conn:
            conn.execute(text("create table other_app (value text)"))
            conn.execute(text("insert into other_app (value) values ('Keep me')"))
        database.run_migrations(eng)
        with eng.connect() as conn:
            assert conn.execute(text("select value from other_app")).scalar() == "Keep me"
            assert conn.execute(text("select count(*) from alembic_version")).scalar() == 1
    finally:
        eng.dispose()


def test_legacy_adoption_uses_frozen_baseline_with_new_revisions(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'future.db'}")
    try:
        _baseline(eng)
        database.run_migrations(eng)
        with eng.connect() as conn:
            assert conn.execute(text("select version_num from alembic_version")).scalar() == "0002"
        assert len(inspect(eng).get_check_constraints("assessments")) == 2
    finally:
        eng.dispose()


def _seed_baseline(eng):
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO courses VALUES ('c', 'Math')"))
        conn.execute(text("INSERT INTO sections VALUES ('sec', 'c', 'A')"))
        conn.execute(text("INSERT INTO students VALUES ('s', 'Student', 8, 'sec')"))
        conn.execute(text("INSERT INTO assessments VALUES ('a', 'sec', 'Test', 'test', 100, '2026-10-01')"))
        conn.execute(text("INSERT INTO scores VALUES ('score', 'a', 's', 125)"))
        conn.execute(text("INSERT INTO attendance VALUES ('att', 's', '2026-10-01', 'present')"))
        conn.execute(text("INSERT INTO notes VALUES ('n', 's', 'Keep this note', '2026-10-01')"))
        conn.execute(text("INSERT INTO insights VALUES ('s', 'fingerprint', 'rules', '{}', '2026-10-01')"))


def _rows(eng):
    with eng.connect() as conn:
        return {
            name: conn.execute(text(f'SELECT * FROM "{name}" ORDER BY 1')).all()
            for name in database.Base.metadata.tables
        }


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("cli", [False, True])
def test_integrity_upgrade_preserves_every_row_with_foreign_keys_enabled(tmp_path, versioned, cli):
    eng = database.make_engine(f"sqlite:///{tmp_path / 'preserve.db'}")
    try:
        _baseline(eng)
        _seed_baseline(eng)
        if versioned:
            with eng.begin() as conn:
                conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
                conn.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
        before = _rows(eng)
        if cli and versioned:
            cfg = Config(str(database.ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(database.ROOT / "alembic"))
            with eng.connect() as conn:
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
        else:
            database.run_migrations(eng)
        assert _rows(eng) == before
        with eng.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
    finally:
        eng.dispose()


@pytest.mark.parametrize(
    ("table", "column", "invalid"),
    [
        ("students", "grade_level", 13),
        ("students", "grade_level", 1.5),
        ("assessments", "max_points", 0),
        ("assessments", "kind", "exam"),
        ("scores", "points", -1),
        ("scores", "points", float("inf")),
        ("attendance", "status", "unknown"),
    ],
)
def test_invalid_legacy_rows_stop_upgrade_without_changing_data_or_schema(tmp_path, table, column, invalid):
    eng = database.make_engine(f"sqlite:///{tmp_path / 'invalid.db'}")
    try:
        _baseline(eng)
        _seed_baseline(eng)
        with eng.begin() as conn:
            conn.execute(text(f"UPDATE {table} SET {column} = :invalid"), {"invalid": invalid})
        before_rows = _rows(eng)
        before_shape = _shape(eng)
        with pytest.raises(RuntimeError, match="Existing data has not been changed"):
            database.run_migrations(eng)
        assert _rows(eng) == before_rows
        assert _shape(eng) == before_shape
        with eng.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        eng.dispose()


def test_legacy_foreign_key_violation_is_rejected_before_schema_changes(tmp_path):
    eng = database.make_engine(f"sqlite:///{tmp_path / 'bad-fk.db'}")
    try:
        _baseline(eng)
        _seed_baseline(eng)
        with eng.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.execute(text("UPDATE students SET section_id = 'missing'"))
            conn.commit()
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()
        before_rows = _rows(eng)
        before_shape = _shape(eng)
        with pytest.raises(RuntimeError, match="foreign key violations"):
            database.run_migrations(eng)
        assert _rows(eng) == before_rows
        assert _shape(eng) == before_shape
        with eng.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        eng.dispose()
