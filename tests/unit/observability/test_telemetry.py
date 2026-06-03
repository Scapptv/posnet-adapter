"""AI-1.13 — libs/observability tracing + metrics (unit, in-memory exporter).

All spans go to an explicit in-memory provider (no OTLP, no network); providers
are passed explicitly to the instrumentations so these tests never depend on the
process-global tracer provider.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from libs.observability import (
    TelemetryConfig,
    add_trace_context,
    build_tracer_provider,
    current_trace_id,
    instrument_fastapi,
    setup_metrics,
    setup_telemetry,
)


def _config(**overrides: object) -> TelemetryConfig:
    base: dict[str, object] = {
        "service_name": "posnet-test",
        "environment": "local",
        "exporter_endpoint": "http://localhost:4317",
    }
    base.update(overrides)
    return TelemetryConfig(**base)  # type: ignore[arg-type]


def _ping_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def _ping() -> dict[str, bool]:
        return {"ok": True}

    return app


# ---- tracer provider ----


@pytest.mark.unit
def test_build_tracer_provider_otlp_default() -> None:
    # exporter=None -> OTLP exporter constructed (lazy; no connection/export here).
    provider = build_tracer_provider(_config())
    assert isinstance(provider, TracerProvider)
    assert provider.resource.attributes[SERVICE_NAME] == "posnet-test"
    assert provider.resource.attributes["deployment.environment"] == "local"


@pytest.mark.unit
def test_build_tracer_provider_exports_to_exporter() -> None:
    exporter = InMemorySpanExporter()
    provider = build_tracer_provider(_config(), exporter=exporter)
    provider.get_tracer("t").start_span("unit-span").end()
    assert len(exporter.get_finished_spans()) == 1


# ---- trace context helpers ----


@pytest.mark.unit
def test_current_trace_id_none_without_span() -> None:
    assert current_trace_id() is None


@pytest.mark.unit
def test_current_trace_id_in_span() -> None:
    provider = build_tracer_provider(_config(), exporter=InMemorySpanExporter())
    with provider.get_tracer("t").start_as_current_span("s"):
        trace_id = current_trace_id()
    assert trace_id is not None
    assert len(trace_id) == 32  # 16-byte trace id, hex


@pytest.mark.unit
def test_add_trace_context_no_span() -> None:
    assert add_trace_context(None, "info", {"event": "x"}) == {"event": "x"}  # type: ignore[arg-type]


@pytest.mark.unit
def test_add_trace_context_in_span() -> None:
    provider = build_tracer_provider(_config(), exporter=InMemorySpanExporter())
    with provider.get_tracer("t").start_as_current_span("s"):
        out = add_trace_context(None, "info", {"event": "x"})  # type: ignore[arg-type]
    assert len(out["trace_id"]) == 32
    assert len(out["span_id"]) == 16


# ---- instrumentation + metrics ----


@pytest.mark.unit
def test_instrument_fastapi_creates_server_span() -> None:
    exporter = InMemorySpanExporter()
    app = _ping_app()
    instrument_fastapi(app, build_tracer_provider(_config(), exporter=exporter))
    with TestClient(app) as client:
        assert client.get("/ping").status_code == 200
    assert any(span.kind == SpanKind.SERVER for span in exporter.get_finished_spans())


@pytest.mark.unit
def test_setup_metrics_exposes_prometheus() -> None:
    app = _ping_app()
    setup_metrics(app)
    with TestClient(app) as client:
        client.get("/ping")
        metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "# TYPE" in metrics.text  # prometheus exposition format


@pytest.mark.unit
def test_setup_telemetry_wires_tracing_and_metrics() -> None:
    exporter = InMemorySpanExporter()
    app = _ping_app()
    provider = setup_telemetry(app, _config(), span_exporter=exporter)
    assert isinstance(provider, TracerProvider)
    with TestClient(app) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/metrics").status_code == 200
    assert exporter.get_finished_spans()  # the /ping request was traced
