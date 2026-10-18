import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ecosys:ecosys@localhost:5432/ecosys_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "fake"
os.environ["AUTH_MODE"] = "dev"
os.environ["BOOTSTRAP_ADMINS"] = "admin@ecosys.test"

import pytest  # noqa: E402
from arq import create_pool  # noqa: E402
from arq.connections import RedisSettings  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.asyncio import Redis  # noqa: E402

from app import models  # noqa: E402,F401
from app.auth.tokens import mint_dev_token  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.content.seed import seed_content  # noqa: E402
from app.db import Base, get_engine, sessionmaker  # noqa: E402
from app.engine import critic  # noqa: E402,F401
from app.gateway.providers import FakeProvider, set_provider  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def database():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with sessionmaker()() as s:
        await seed_content(s)
    set_provider(FakeProvider(delay=0))
    yield
    await engine.dispose()


@pytest.fixture(scope="session")
async def redis():
    r = Redis.from_url(get_settings().redis_url)
    await r.flushdb()
    yield r
    await r.aclose()


@pytest.fixture(scope="session")
async def client(redis):
    app.state.redis = redis
    app.state.arq = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await app.state.arq.aclose()


def auth(email: str, name: str = "Test", roles: list[str] | None = None) -> dict:
    return {"Authorization": f"Bearer {mint_dev_token(email, name, roles)}"}


async def run_now(redis, run_id: str) -> None:
    """Execute a queued run inline (what the arq worker does)."""
    import uuid

    from app.engine.runner import execute_run
    from app.gateway.providers import get_provider

    async with sessionmaker()() as session:
        await execute_run(session, redis, get_provider(), uuid.UUID(run_id))
