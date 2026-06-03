"""OpenTelemetry tracing + Prometheus metrics wiring (AI-1.13).

Reusable observability primitives: a tracer provider (OTLP export, configurable
sampling), instrumentations (FastAPI HTTP spans, SQLAlchemy DB spans), a
Prometheus ``/metrics`` endpoint on an isolated registry, and helpers to surface
the active trace id in logs and error bodies. Config arrives as a plain
:class:`TelemetryConfig` (the app maps its settings into it).

Redis/httpx instrumentation is intentionally deferred — their instrumentors are
process-global; the NFR-relevant spans (HTTP via FastAPI, DB via SQLAlchemy) are
covered here.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.types import EventDict, WrappedLogger

_DEPLOYMENT_ENVIRONMENT = "deployment.environment"


@dataclass(frozen=True)
class TelemetryConfig:
    service_name: str
    environment: str
    exporter_endpoint: str
    sampler_ratio: float = 1.0
    exporter_insecure: bool = True


def build_tracer_provider(
    config: TelemetryConfig, *, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Build a TracerProvider. With ``exporter`` (tests) spans flush synchronously;
    otherwise they batch to the OTLP collector."""
    resource = Resource.create(
        {SERVICE_NAME: config.service_name, _DEPLOYMENT_ENVIRONMENT: config.environment}
    )
    provider = TracerProvider(
        resource=resource, sampler=ParentBasedTraceIdRatio(config.sampler_ratio)
    )
    if exporter is None:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=config.exporter_endpoint, insecure=config.exporter_insecure
                )
            )
        )
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def current_trace_id() -> str | None:
    """Hex trace id of the active span, or ``None`` outside a recorded span."""
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return trace.format_trace_id(span_context.trace_id)


def add_trace_context(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: stamp the active trace/span id for log↔trace correlation."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = trace.format_trace_id(span_context.trace_id)
        event_dict["span_id"] = trace.format_span_id(span_context.span_id)
    return event_dict


def instrument_fastapi(
    app: FastAPI, tracer_provider: TracerProvider, *, excluded_urls: str = ""
) -> None:
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, excluded_urls=excluded_urls
    )


def instrument_sqlalchemy(engine: AsyncEngine, tracer_provider: TracerProvider) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=tracer_provider)


def setup_metrics(app: FastAPI, *, excluded_handlers: list[str] | None = None) -> CollectorRegistry:
    """Expose Prometheus ``/metrics`` on a fresh registry (isolated per app)."""
    registry = CollectorRegistry()
    Instrumentator(registry=registry, excluded_handlers=excluded_handlers or []).instrument(
        app
    ).expose(app, endpoint="/metrics", include_in_schema=False)
    return registry


def setup_telemetry(
    app: FastAPI, config: TelemetryConfig, *, span_exporter: SpanExporter | None = None
) -> TracerProvider:
    """Wire tracing + metrics into ``app`` and set the global tracer provider."""
    provider = build_tracer_provider(config, exporter=span_exporter)
    trace.set_tracer_provider(provider)
    instrument_fastapi(app, provider, excluded_urls="healthz,readyz,metrics")
    setup_metrics(app, excluded_handlers=["/healthz", "/readyz", "/metrics"])
    return provider
