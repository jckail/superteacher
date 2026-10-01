from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

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
        )
    return out


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
    database.Base.metadata.create_all(eng)  # how the app created DBs before Alembic
    with eng.begin() as c:
        c.execute(text("insert into courses (id, name) values ('c1', 'Science')"))
    database.run_migrations(eng)
    with eng.connect() as c:
        assert c.execute(text("select name from courses")).scalar() == "Science"
        assert c.execute(text("select count(*) from alembic_version")).scalar() == 1


def test_alembic_files_present():
    root = Path(database.ROOT)
    assert (root / "alembic.ini").is_file() and list((root / "alembic" / "versions").glob("0001_*.py"))
