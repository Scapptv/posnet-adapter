"""AI-1.13 — app telemetry wiring: config mapping + create_app otel gate (unit).

The otel-on case uses ``TestClient(app)`` without the context manager so the
lifespan (and its global SQLAlchemy instrumentation) does not run — HTTP tracing,
the /metrics route and trace-id-in-errors all come from ``create_app`` itself.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from libs.common import NotFoundError
from services.core.app.config import Settings
from services.core.app.main import create_app
from services.core.app.telemetry import build_telemetry_config


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "local",
        "database_url": "postgresql+psycopg://u@localhost/x",
        "redis_url": "redis://localhost:6379/0",
        "eventbus_enabled": False,
        "rate_limit_storage_uri": "memory://",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.unit
def test_build_telemetry_config_from_settings() -> None:
    cfg = build_telemetry_config(
        _settings(
            otel_service_name="svc",
            otel_exporter_otlp_endpoint="http://collector:4317",
            otel_traces_sampler_ratio=0.25,
        )
    )
    assert cfg.service_name == "svc"
    assert cfg.environment == "local"
    assert cfg.exporter_endpoint == "http://collector:4317"
    assert cfg.sampler_ratio == 0.25


@pytest.mark.unit
def test_create_app_without_otel_has_no_metrics() -> None:
    app = create_app(_settings(otel_enabled=False))
    assert app.state.tracer_provider is None
    assert TestClient(app).get("/metrics").status_code == 404


@pytest.mark.unit
def test_create_app_with_otel_traces_metrics_and_error_trace_id() -> None:
    exporter = InMemorySpanExporter()
    app = create_app(_settings(otel_enabled=True), span_exporter=exporter)

    @app.get("/boom-traced")
    async def _boom() -> dict[str, str]:
        raise NotFoundError("widget gone")

    client = TestClient(app)  # no `with` -> skip lifespan / SQLAlchemy instrumentation
    error = client.get("/boom-traced")
    metrics = client.get("/metrics")

    assert app.state.tracer_provider is not None
    assert error.status_code == 404
    assert len(error.json()["trace_id"]) == 32  # trace id surfaced in problem+json
    assert metrics.status_code == 200
    assert exporter.get_finished_spans()  # the request was traced
