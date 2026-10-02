from alembic import context
from superteacher import models  # noqa: F401  (register tables)
from superteacher.config import get_settings
from superteacher.db import Base, validate_revision_identity

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    sqlite_fk = None
    if connection.dialect.name == "sqlite":
        caller_transaction = connection.in_transaction()
        sqlite_fk = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        if sqlite_fk:
            # CLI migrations also need batch table recreation without cascades.
            # A caller with an active SQLite transaction must disable FKs first.
            if caller_transaction:
                raise RuntimeError("SQLite migrations require foreign_keys=OFF before starting a transaction")
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            if sqlite_fk:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
            raise RuntimeError("Database contains foreign key violations; refusing to migrate it.")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs batch mode for ALTERs
        compare_type=True,
    )
    try:
        validate_revision_identity(connection)
        with context.begin_transaction():
            context.run_migrations()
            if (
                connection.dialect.name == "sqlite"
                and connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None
            ):
                raise RuntimeError("Migration found foreign key violations; refusing to accept the database.")
    except Exception:
        if sqlite_fk:
            connection.rollback()
        raise
    finally:
        if sqlite_fk:
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()
elif (conn := config.attributes.get("connection")) is not None:
    _run(conn)  # programmatic call from superteacher.db.run_migrations
else:
    from superteacher.db import make_engine

    eng = make_engine(get_settings().database_url)
    with eng.connect() as connection:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")  # see alembic/versions/0003_accounts.py
            connection.commit()
        _run(connection)
        connection.commit()
