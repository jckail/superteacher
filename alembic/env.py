from alembic import context
from superteacher import models  # noqa: F401  (register tables)
from superteacher.config import get_settings
from superteacher.db import Base

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs batch mode for ALTERs
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
elif (conn := config.attributes.get("connection")) is not None:
    _run(conn)  # programmatic call from superteacher.db.run_migrations
else:
    from superteacher.db import make_engine

    eng = make_engine(get_settings().database_url)
    with eng.connect() as connection:
        _run(connection)
        connection.commit()
