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


def run_migrations(eng: Engine) -> None:
    """Bring the schema to the latest revision. Never drops data.

    * In-memory SQLite (tests): ``create_all``.
    * File/server DBs: ``alembic upgrade head``. A database created before Alembic was introduced
      (tables present, no ``alembic_version``) is stamped at the baseline revision first.
    """
    from . import models  # noqa: F401  (register tables)

    if is_memory(eng):
        Base.metadata.create_all(eng)
        return

    from alembic.config import Config
    from sqlalchemy import inspect

    from alembic import command

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    sqlite = eng.dialect.name == "sqlite"
    with eng.connect() as conn:
        if sqlite:
            # Batch migrations recreate tables; with FKs on, DROP TABLE would cascade-delete child rows.
            # The pragma is a no-op inside a transaction, so it is switched off before one starts.
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()
        try:
            with conn.begin():
                cfg.attributes["connection"] = conn
                tables = set(inspect(conn).get_table_names())
                if "alembic_version" not in tables and tables & set(Base.metadata.tables):
                    command.stamp(cfg, BASELINE_REVISION)
                command.upgrade(cfg, "head")
                if sqlite and conn.exec_driver_sql("PRAGMA foreign_key_check").first():
                    raise RuntimeError("Migration left foreign key violations; rolled back.")
        finally:
            if sqlite:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                conn.commit()


BASELINE_REVISION = "0001"
