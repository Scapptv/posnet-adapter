"""AI-1.13 — app telemetry over the real lifespan: HTTP + DB spans.

Runs ``create_app(otel_enabled=True)`` through the actual ``lifespan`` (which
instruments the live SQLAlchemy engine) and drives a request that touches the DB.
The instrumentation singletons are reset in ``finally`` so nothing leaks to other
tests.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy import text

from services.core.app.config import Settings
from services.core.app.main import create_app, lifespan


@pytest.mark.integration
async def test_app_telemetry_traces_http_and_db(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    exporter = InMemorySpanExporter()
    # Split app pool (posnet_app) — the realistic deployment shape; both engines
    # get DB-span instrumentation (ADR-0017). The DB ping below runs on it.
    app_creds = "posnet_app:posnet_app_dev_pw"  # pragma: allowlist secret
    parts = urlsplit(pg_sqlalchemy_url)
    app_pool_url = urlunsplit(
        (parts.scheme, f"{app_creds}@{parts.hostname}:{parts.port}", parts.path, "", "")
    )
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_sqlalchemy_url,
            database_app_url=app_pool_url,
            redis_url=redis_url,
            otel_enabled=True,
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        ),
        span_exporter=exporter,
    )

    @app.get("/db-ping")
    async def _db_ping() -> dict[str, int]:
        async with app.state.sessionmaker() as session:
            value = (await session.execute(text("SELECT 1"))).scalar_one()
        return {"value": int(value)}

    try:
        async with lifespan(app):  # instruments the live engine for DB spans
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/db-ping")

        assert response.status_code == 200
        assert response.json() == {"value": 1}
        kinds = {span.kind for span in exporter.get_finished_spans()}
        assert SpanKind.SERVER in kinds  # the HTTP request span
        assert SpanKind.CLIENT in kinds  # the SQLAlchemy DB span
    finally:
        FastAPIInstrumentor.uninstrument_app(app)
        SQLAlchemyInstrumentor().uninstrument()
