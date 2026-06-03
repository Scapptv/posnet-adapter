"""App-side telemetry wiring (AI-1.13) — map ``Settings`` into TelemetryConfig.

``libs/observability`` stays settings-agnostic (a plain ``TelemetryConfig``); the
app is where env/OTel settings become that config (same pattern as auth/eventbus).
"""

from __future__ import annotations

from libs.observability import TelemetryConfig

from .config import Settings


def build_telemetry_config(settings: Settings) -> TelemetryConfig:
    return TelemetryConfig(
        service_name=settings.otel_service_name,
        environment=settings.environment,
        exporter_endpoint=settings.otel_exporter_otlp_endpoint,
        sampler_ratio=settings.otel_traces_sampler_ratio,
    )
