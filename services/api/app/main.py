from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api import admin, course, manage, me, social, workspace
from app.config import get_settings
from app.db import dispose_engine
from app.telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq.aclose()
    await app.state.redis.aclose()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_telemetry("ecosys-api")
    app = FastAPI(title="Ecosys API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (me.router, course.router, workspace.router, social.router, manage.router, admin.router):
        app.include_router(r)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True, "provider": settings.model_provider, "auth": settings.auth_mode}

    return app


app = create_app()
