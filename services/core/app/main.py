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
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from slowapi.middleware import SlowAPIASGIMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from libs.eventbus import EventHandler

from .api.health import router as health_router
from .config import Settings, get_settings
from .errors import register_exception_handlers
from .eventbus_workers import EventBusWorkers, build_eventbus_config, log_event_handler
from .logging_config import configure_logging
from .middleware.logging import LoggingMiddleware
from .middleware.request_id import RequestIdMiddleware
from .middleware.security import SecurityHeadersMiddleware
from .rate_limit import build_limiter, exempt_routes
from .security import build_token_verifier


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
    # JWT verifier shares the app Redis for JWKS caching (AI-1.9.3).
    app.state.token_verifier = build_token_verifier(settings, redis)

    # EventBus relay + consumer on the owner (RLS-exempt) session factory — the
    # cross-tenant role they need to drain every tenant's outbox (AI-1.9.5).
    workers: EventBusWorkers | None = None
    if settings.eventbus_enabled:
        workers = EventBusWorkers(
            app.state.sessionmaker, build_eventbus_config(settings), app.state.event_handler
        )
        await workers.ensure_queues(engine)
        workers.start()
    app.state.eventbus_workers = workers

    try:
        yield
    finally:
        if workers is not None:
            await workers.stop()
        await redis.aclose()
        await engine.dispose()


def create_app(
    settings: Settings | None = None, *, event_handler: EventHandler | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json_logs=settings.environment != "local")

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    # Consumed by the lifespan; foundation default just logs (AI-2 injects a dispatcher).
    app.state.event_handler = event_handler or log_event_handler

    register_exception_handlers(app)

    # Rate limiter lives on app.state; health probes are exempt (infra polls them).
    limiter = build_limiter(settings)
    app.state.limiter = limiter
    exempt_routes(limiter, health_router.routes)

    # add_middleware prepends, so the last added is outermost. Target order
    # (outer -> inner): RequestId -> Logging -> CORS -> SecurityHeaders -> RateLimit -> app.
    # RequestId stays outermost so even a 429/CORS response carries a request id.
    app.add_middleware(SlowAPIASGIMiddleware)
    if settings.security_headers_enabled:
        app.add_middleware(
            SecurityHeadersMiddleware, csp=settings.security_csp, hsts=settings.security_hsts
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=settings.cors_max_age,
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    return app
