import asyncio
from logging.config import fileConfig

from alembic import context
from app import models  # noqa: F401 — registers tables on Base.metadata
from app.db import Base, dispose_engine, get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    from app.config import get_settings

    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Reuses the app engine so passwordless (Entra) Postgres auth works for migrations too.
    async with get_engine().connect() as connection:
        await connection.run_sync(do_run_migrations)
    await dispose_engine()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
