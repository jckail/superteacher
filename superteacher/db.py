from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        file_backed = not ("://" in url and ":memory:" in url) and url not in ("sqlite://", "sqlite:///")

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs unless asked
            if file_backed:
                # WAL: readers don't block the writer, and it is what Litestream replicates (it needs WAL mode).
                # synchronous=NORMAL is the recommended pairing with WAL; busy_timeout rides out brief write locks.
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA synchronous=NORMAL")
                dbapi_conn.execute("PRAGMA busy_timeout=5000")

    return eng


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


ROOT = Path(__file__).resolve().parent.parent


def is_memory(eng: Engine) -> bool:
    return eng.dialect.name == "sqlite" and eng.url.database in (None, "", ":memory:")


def run_migrations(eng: Engine, *, target_revision: str = "head") -> None:
    """Bring the schema to the latest revision. Never drops data.

    * In-memory SQLite (tests): ``create_all``.
    * File/server DBs: ``alembic upgrade head`` by default. Archive generation explicitly
      selects its frozen ``0003`` format; it does not follow the runtime head.
      A database created before Alembic was introduced
      (tables present, no ``alembic_version``) is stamped at the baseline revision first.
    * PostgreSQL takes a transaction advisory lock before that revision check so
      overlapping processes apply DDL one at a time. SQLite does not.
    """
    from . import models  # noqa: F401  (register tables)

    if is_memory(eng):
        if target_revision != "head":
            raise ValueError("An explicit migration target requires a file or server database.")
        Base.metadata.create_all(eng)
        return

    from alembic.config import Config
    from sqlalchemy import inspect

    from alembic import command

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    with eng.connect() as conn:
        # SQLite batch migrations recreate parent tables. Disable cascades before
        # any transaction, otherwise dropping the old table would delete child rows.
        sqlite_fk = None
        if eng.dialect.name == "sqlite":
            sqlite_fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()
        try:
            with conn.begin():
                if eng.dialect.name == "postgresql":
                    conn.exec_driver_sql(
                        "SELECT pg_advisory_xact_lock(CAST(%s AS bigint))",
                        (POSTGRES_MIGRATION_ADVISORY_LOCK,),
                    )
                cfg.attributes["connection"] = conn
                tables = set(inspect(conn).get_table_names())
                validate_revision_identity(conn)
                if "alembic_version" not in tables and tables & set(Base.metadata.tables):
                    _validate_legacy_schema(conn)
                    command.stamp(cfg, BASELINE_REVISION)
                command.upgrade(cfg, target_revision)
                if sqlite_fk is not None and conn.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                    raise RuntimeError("Migration found foreign key violations; refusing to accept the database.")
        finally:
            if sqlite_fk is not None:
                conn.exec_driver_sql(f"PRAGMA foreign_keys={int(sqlite_fk)}")
                conn.commit()


BASELINE_REVISION = "0001"
# Database-wide, transaction-scoped. Overlapping PostgreSQL boots take this before
# reading alembic_version so they cannot apply the same DDL together. It releases
# on commit or rollback and works behind a transaction-mode pooler.
POSTGRES_MIGRATION_ADVISORY_LOCK = 838_338_091


def validate_revision_identity(conn) -> None:
    """Reject the independently published accounts 0002 before any migration DDL.

    Native 0002 means integrity constraints; accounts 0002 has a different schema.
    Its adoption requires a verified backup and an explicit separate migration.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables:
        return
    revisions = set(conn.execute(text("SELECT version_num FROM alembic_version")).scalars())
    if "0002" not in revisions:
        return
    account_tables = {"users", "sessions", "login_tokens", "usage_counters", "ai_budget"}
    owner_column = "courses" in tables and any(
        column["name"] == "owner_id" for column in inspector.get_columns("courses")
    )
    required = {
        "students": {"ck_students_grade_level"},
        "assessments": {"ck_assessments_max_points", "ck_assessments_kind"},
        "scores": {"ck_scores_points"},
        "attendance": {"ck_attendance_status"},
    }
    integrity_present = all(
        table in tables and names <= {check["name"] for check in inspector.get_check_constraints(table)}
        for table, names in required.items()
    )
    if tables & account_tables or owner_column or not integrity_present:
        raise RuntimeError(
            "Ambiguous revision 0002: this database does not match native integrity 0002. "
            "The independently published accounts 0002 requires an explicit backup/adoption migration; "
            "refusing to migrate or stamp it. Existing data has not been changed."
        )


def _validate_legacy_schema(conn) -> None:
    """Only adopt a complete supported legacy schema; stamping must never conceal drift.

    Unrelated tables may coexist; app tables, columns and constraints must match.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import DateTime, Enum, MetaData

    # Derive the frozen baseline from revision 0001 itself, independently of the
    # evolving models. This keeps adoption correct as later revisions are added.
    from alembic import command

    baseline = MetaData()
    baseline_engine = create_engine("sqlite://")
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        with baseline_engine.begin() as baseline_conn:
            cfg.attributes["connection"] = baseline_conn
            command.upgrade(cfg, BASELINE_REVISION)
            baseline.reflect(baseline_conn, only=lambda name, _: name != "alembic_version")
    finally:
        baseline_engine.dispose()
    # SQLite reflection yields VARCHAR for enum columns. Retain the exact native
    # enum definitions from 0001 when comparing against PostgreSQL legacy DBs.
    baseline.tables["assessments"].c.kind.type = Enum("test", "quiz", "homework", "project", name="assessmentkind")
    baseline.tables["attendance"].c.status.type = Enum("present", "tardy", "absent", "excused", name="attendancestatus")
    for table in ("notes", "insights"):
        baseline.tables[table].c.created_at.type = DateTime(timezone=True)

    def include_object(obj, name, kind, reflected, compare_to):
        return kind != "table" or name in baseline.tables

    context = MigrationContext.configure(conn, opts={"compare_type": True, "include_object": include_object})
    if compare_metadata(context, baseline):
        raise RuntimeError(
            "Legacy database schema does not match the supported baseline; refusing to stamp it. "
            "Review the schema and restore or migrate the database explicitly. Existing data has not been changed."
        )
