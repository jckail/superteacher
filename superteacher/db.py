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

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite ignores FKs unless asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

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
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and tables & set(Base.metadata.tables):
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


BASELINE_REVISION = "0001"
