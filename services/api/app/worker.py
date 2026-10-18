"""arq worker that executes runs.  Start with: arq app.worker.WorkerSettings"""

import uuid

from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import get_settings
from app.db import dispose_engine, sessionmaker
from app.engine import critic  # noqa: F401 — registers the fake critic handler
from app.engine.runner import execute_run
from app.gateway.providers import get_provider
from app.telemetry import setup_telemetry


async def run_job(ctx, run_id: str) -> None:
    async with sessionmaker()() as session:
        await execute_run(session, ctx["redis_pub"], get_provider(), uuid.UUID(run_id))


async def startup(ctx) -> None:
    setup_telemetry("ecosys-worker")
    ctx["redis_pub"] = Redis.from_url(get_settings().redis_url)


async def shutdown(ctx) -> None:
    await ctx["redis_pub"].aclose()
    await dispose_engine()


class WorkerSettings:
    functions = [run_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 40  # runs are I/O bound (streaming from Foundry)
    job_timeout = 300
    max_tries = 2
