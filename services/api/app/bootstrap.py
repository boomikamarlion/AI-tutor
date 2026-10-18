"""Container start-up: migrate and seed content under a Postgres advisory lock, so several API
replicas starting at once never run migrations concurrently.  Usage: python -m app.bootstrap"""

import asyncio
import logging

from sqlalchemy import text

from app.content.seed import seed_content
from app.db import dispose_engine, get_engine, sessionmaker

LOCK_ID = 7_420_261  # arbitrary, stable

log = logging.getLogger("bootstrap")


def _upgrade(sync_conn) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = sync_conn
    command.upgrade(cfg, "head")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": LOCK_ID})
        try:
            await conn.run_sync(_upgrade)
            await conn.commit()
            async with sessionmaker()() as session:
                log.info("content: %s", await seed_content(session))
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
            await conn.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
