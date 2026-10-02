from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from superteacher import db as database
from superteacher import models  # noqa: F401
from superteacher.db import ROOT


def upgrade_to(eng, revision: str) -> None:
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)


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
        c.execute(
            text("insert into users (id, email, disabled, created_at) values ('u1', 'a@b.co', 0, CURRENT_TIMESTAMP)")
        )
        c.execute(text("insert into courses (id, name, owner_id) values ('c1', 'Math', 'u1')"))
    database.run_migrations(eng)  # second startup
    with eng.connect() as c:
        assert c.execute(text("select name from courses")).scalar() == "Math"


def test_legacy_db_without_alembic_version_is_stamped_not_recreated(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    upgrade_to(eng, "0001")  # a pre-Alembic database: the 0001 schema without an alembic_version table
    with eng.begin() as c:
        c.execute(text("drop table alembic_version"))
        c.execute(text("insert into courses (id, name) values ('c1', 'Science')"))
    database.run_migrations(eng)
    with eng.connect() as c:
        assert c.execute(text("select name from courses")).scalar() == "Science"
        assert c.execute(text("select count(*) from alembic_version")).scalar() == 1


def test_alembic_files_present():
    root = Path(database.ROOT)
    assert (root / "alembic.ini").is_file() and list((root / "alembic" / "versions").glob("0001_*.py"))


def test_owner_name_uniqueness_is_case_insensitive_per_owner(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'u.db'}")
    database.run_migrations(eng)
    with eng.begin() as c:
        for u in ("u1", "u2"):
            c.execute(
                text(
                    f"insert into users (id, email, disabled, created_at) values ('{u}', '{u}@x.co', 0, CURRENT_TIMESTAMP)"
                )
            )
        c.execute(text("insert into courses (id, name, owner_id) values ('c1', 'Algebra', 'u1')"))
        c.execute(text("insert into courses (id, name, owner_id) values ('c2', 'Algebra', 'u2')"))  # other owner: fine
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), eng.begin() as c:
        c.execute(text("insert into courses (id, name, owner_id) values ('c3', 'ALGEBRA', 'u1')"))


def test_upgrade_from_0001_backfills_existing_rows_to_the_owner(tmp_path):
    eng = database.make_engine(f"sqlite:///{tmp_path / 'old.db'}")  # the real engine: foreign keys ON
    upgrade_to(eng, "0001")
    with eng.begin() as c:
        c.execute(text("insert into courses (id, name) values ('c1', 'Algebra'), ('c2', 'History')"))
        c.execute(text("insert into sections (id, course_id, name) values ('s1', 'c1', 'P1')"))
        c.execute(text("insert into students (id, name, grade_level, section_id) values ('st1', 'Ada', 9, 's1')"))
    database.run_migrations(eng)  # 0001 -> head with data present
    with eng.connect() as c:
        owner = c.execute(text("select id, email from users")).all()
        assert owner == [(models.OWNER_ID, models.OWNER_EMAIL)]
        assert c.execute(text("select owner_id from courses")).scalars().all() == [models.OWNER_ID] * 2
        assert (
            c.execute(text("select count(*) from sections")).scalar() == 1
        )  # no cascade damage from the table rebuild
        assert c.execute(text("select count(*) from students")).scalar() == 1
        assert c.execute(text("select name from sqlite_master where name='uq_courses_owner_name'")).scalar()


def test_fresh_database_has_no_owner_user(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    database.run_migrations(eng)
    with eng.connect() as c:
        assert c.execute(text("select count(*) from users")).scalar() == 0
