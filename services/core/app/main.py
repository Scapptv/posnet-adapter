"""FastAPI application factory (AI-1.9.1).

``create_app`` builds the app from an explicit ``Settings`` (so tests can point
it at testcontainers without touching global state). The lifespan owns the
shared async resources — the SQLAlchemy engine and the Redis client — and
exposes them on ``app.state`` for request handlers and dependencies.

Middleware stack (LOCKED order, filled in by the AI-1.9.* slices):
RequestId -> Logging -> Tracing -> Auth -> TenantContext -> RateLimit -> ErrorHandler.
The eventbus relay/consumer wiring (AI-1.9.5) waits on the relay's cross-tenant
DB role (AI-1.14 follow-up) and is intentionally not started here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .api.health import router as health_router
from .config import Settings, get_settings
from .errors import register_exception_handlers
from .logging_config import configure_logging
from .middleware.logging import LoggingMiddleware
from .middleware.request_id import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    redis: Redis = Redis.from_url(settings.redis_url)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json_logs=settings.environment != "local")

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings

    register_exception_handlers(app)
    # add_middleware prepends, so the last added is outermost: RequestId wraps
    # Logging wraps the app — request_id is set before the access log runs.
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    return app
