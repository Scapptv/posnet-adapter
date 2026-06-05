"""FastAPI application factory (AI-1.9.1).

``create_app`` builds the app from an explicit ``Settings`` (so tests can point
it at testcontainers without touching global state). The lifespan owns the
shared async resources — the SQLAlchemy engine, the Redis client and the
eventbus workers — and exposes them on ``app.state`` for handlers/dependencies.

Middleware/request pipeline (LOCKED order): RequestId -> Logging -> Tracing(OTel)
-> Auth -> TenantContext -> RateLimit -> ErrorHandler. Auth/TenantContext are
dependencies; Tracing is the OTel FastAPI instrumentation (AI-1.13, opt-in).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.sdk.trace.export import SpanExporter
from redis.asyncio import Redis
from slowapi.middleware import SlowAPIASGIMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from libs.eventbus import EventHandler
from libs.observability import instrument_sqlalchemy, setup_telemetry

from .api.health import router as health_router
from .api.v1 import api_router
from .config import Settings, get_settings
from .errors import register_exception_handlers
from .eventbus_workers import EventBusWorkers, build_eventbus_config, log_event_handler
from .i18n import build_translator
from .idempotency import idempotent
from .logging_config import configure_logging
from .middleware.logging import LoggingMiddleware
from .middleware.request_id import RequestIdMiddleware
from .middleware.security import SecurityHeadersMiddleware
from .rate_limit import build_limiter, exempt_routes
from .security import build_token_verifier
from .sync.wiring import (
    build_dispatcher,
    build_webhook_adapter_factory,
    register_builtin_adapters,
)
from .telemetry import build_telemetry_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    def _engine(url: str):  # type: ignore[no-untyped-def]
        return create_async_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
        )

    # System/privileged pool (superuser): migrations are already applied; this
    # pool serves cross-tenant work — eventbus workers, super_admin, onboarding.
    system_engine = _engine(settings.database_url)
    # App pool (non-owner ``posnet_app``): the per-request tenant-scoped path.
    # Empty DATABASE_APP_URL falls back to the system pool (dev/test) — ADR-0017.
    app_engine = _engine(settings.database_app_url) if settings.database_app_url else system_engine

    redis: Redis = Redis.from_url(settings.redis_url)
    app.state.engine = system_engine
    app.state.app_engine = app_engine
    app.state.system_sessionmaker = async_sessionmaker(system_engine, expire_on_commit=False)
    app.state.sessionmaker = async_sessionmaker(app_engine, expire_on_commit=False)
    app.state.redis = redis
    # JWT verifier shares the app Redis for JWKS caching (AI-1.9.3).
    app.state.token_verifier = build_token_verifier(settings, redis)

    # DB span instrumentation needs the live engine(s) (AI-1.13). Dedupe so the
    # fallback (single shared engine) is instrumented once, a split pool twice.
    if settings.otel_enabled and app.state.tracer_provider is not None:
        for db_engine in dict.fromkeys((system_engine, app_engine)):
            instrument_sqlalchemy(db_engine, app.state.tracer_provider)

    # EventBus relay + consumer on the system (RLS-exempt) session factory — the
    # cross-tenant role they need to drain every tenant's outbox (AI-1.9.5, ADR-0017).
    workers: EventBusWorkers | None = None
    if settings.eventbus_enabled:
        workers = EventBusWorkers(
            app.state.system_sessionmaker, build_eventbus_config(settings), app.state.event_handler
        )
        await workers.ensure_queues(system_engine)
        workers.start()
    app.state.eventbus_workers = workers

    # Startup complete: advertise readiness (gates /readyz, AI-1.18).
    app.state.ready = True
    try:
        yield
    finally:
        # Drain first: stop passing readiness so the orchestrator removes us from
        # rotation before we tear down, letting in-flight requests finish.
        app.state.ready = False
        if workers is not None:
            await workers.stop()
        await redis.aclose()
        await system_engine.dispose()
        if app_engine is not system_engine:
            await app_engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    event_handler: EventHandler | None = None,
    span_exporter: SpanExporter | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json_logs=settings.environment != "local")

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    # H6 (ADR-0020): for a deployable service, wire the SyncDispatcher as the
    # consumer's handler + the webhook adapter factory off the adapter registry,
    # so an outbox event fans out to every active channel's adapter. Tests inject
    # their own event_handler/factory and skip this (sync_enabled off by default).
    if event_handler is None and settings.sync_enabled:
        register_builtin_adapters()
        event_handler = build_dispatcher(settings)
        app.state.webhook_adapter_factory = build_webhook_adapter_factory(settings)
    # Every consumer handler runs inside the idempotency wrapper (AI-2.H4, audit
    # B5): at-least-once delivery means a redelivered event_id must short-circuit
    # before the handler's external side effect.
    app.state.event_handler = idempotent(event_handler or log_event_handler)
    app.state.tracer_provider = None  # set by setup_telemetry below (if enabled)
    # Process-wide, content-only — built once (no IO), shared by i18n requests.
    app.state.translator = build_translator()
    # Flipped True at the end of lifespan startup, False on shutdown (AI-1.18);
    # /readyz reports not-ready until then.
    app.state.ready = False

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
    app.include_router(api_router)

    # OTel tracing + Prometheus /metrics (AI-1.13). Last, so the FastAPI span wraps
    # the whole middleware stack; the SQLAlchemy engine is instrumented in lifespan.
    if settings.otel_enabled:
        app.state.tracer_provider = setup_telemetry(
            app, build_telemetry_config(settings), span_exporter=span_exporter
        )

    return app
