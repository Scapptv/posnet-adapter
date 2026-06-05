"""AI-2.5.6.3 — sync observability: OTel spans + Prometheus metrics.

Spans are captured by monkeypatching ``trace.get_tracer`` onto a local
in-memory provider (no process-global tracer state, so order-independent).
Metrics are read back via ``SYNC_REGISTRY.get_sample_value`` with unique label
values per test so the module-global registry doesn't leak counts between tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import opentelemetry.trace as ot_trace
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from libs.adapter import AdapterPermanentError, AdapterRetryableError
from services.core.app.infrastructure.db.models import Channel
from services.core.app.sync.dispatcher import _SKIPPED, DispatcherConfig, SyncDispatcher
from services.core.app.sync.observability import (
    SYNC_REGISTRY,
    collect_dlq_depth,
    observe_sync_lag,
    record_push,
    render_sync_metrics,
    set_dlq_depth,
    sync_span,
)


@pytest.fixture
def captured_spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    """Route every ``trace.get_tracer`` to a fresh in-memory provider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(ot_trace, "get_tracer", lambda name: provider.get_tracer(name))
    yield exporter


def _push_total(channel_code: str, operation: str, outcome: str) -> float | None:
    return SYNC_REGISTRY.get_sample_value(
        "posnet_sync_push_total",
        {"channel_code": channel_code, "operation": operation, "outcome": outcome},
    )


def _dispatcher() -> SyncDispatcher:
    async def _factory(_channel: Channel) -> object:  # never used by _guard
        raise AssertionError("factory not used in _guard tests")

    return SyncDispatcher(
        adapter_factory=_factory,  # type: ignore[arg-type]
        config=DispatcherConfig(rate_per_second=1000, rate_burst=100),
    )


def _channel(code: str) -> Channel:
    channel = Channel(tenant_id=uuid4(), code=code, name=code, status="active")
    channel.id = uuid4()  # transient id (no DB) — guard keys its bucket on it
    return channel


# ----------------------------------------------------------------
# sync_span
# ----------------------------------------------------------------


@pytest.mark.unit
def test_sync_span_emits_named_span_with_attributes(
    captured_spans: InMemorySpanExporter,
) -> None:
    with sync_span("channel.push", channel_code="mock", operation="push_stock", missing=None):
        pass
    spans = captured_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "channel.push"
    assert spans[0].attributes is not None
    assert spans[0].attributes["channel_code"] == "mock"
    assert spans[0].attributes["operation"] == "push_stock"
    assert "missing" not in spans[0].attributes  # None dropped


# ----------------------------------------------------------------
# _guard span + push-outcome metric
# ----------------------------------------------------------------


@pytest.mark.unit
async def test_guard_success_records_span_and_success_metric(
    captured_spans: InMemorySpanExporter,
) -> None:
    dispatcher = _dispatcher()
    channel = _channel("obs-ok")

    async def _op() -> str:
        return "done"

    result = await dispatcher._guard(channel, _op, "push_stock")

    assert result == "done"
    spans = captured_spans.get_finished_spans()
    assert spans[0].name == "channel.push"
    assert spans[0].attributes is not None
    assert spans[0].attributes["operation"] == "push_stock"
    assert _push_total("obs-ok", "push_stock", "success") == 1.0


@pytest.mark.unit
async def test_guard_retryable_records_metric_and_reraises(
    captured_spans: InMemorySpanExporter,
) -> None:
    dispatcher = _dispatcher()
    channel = _channel("obs-retry")

    async def _op() -> None:
        raise AdapterRetryableError("boom")

    with pytest.raises(AdapterRetryableError):
        await dispatcher._guard(channel, _op, "push_listing")

    assert _push_total("obs-retry", "push_listing", "retryable") == 1.0


@pytest.mark.unit
async def test_guard_permanent_records_metric_and_swallows(
    captured_spans: InMemorySpanExporter,
) -> None:
    dispatcher = _dispatcher()
    channel = _channel("obs-perm")

    async def _op() -> None:
        raise AdapterPermanentError("nope")

    result = await dispatcher._guard(channel, _op, "push_price")

    assert result is _SKIPPED  # swallowed → sentinel (C2, ADR-0020)
    assert _push_total("obs-perm", "push_price", "permanent") == 1.0


# ----------------------------------------------------------------
# metric helpers
# ----------------------------------------------------------------


@pytest.mark.unit
def test_observe_sync_lag_records_observation() -> None:
    observe_sync_lag(event_type="obs.lag.evt", seconds=1.5)
    count = SYNC_REGISTRY.get_sample_value(
        "posnet_sync_lag_seconds_count", {"event_type": "obs.lag.evt"}
    )
    assert count == 1.0


@pytest.mark.unit
def test_observe_sync_lag_clamps_negative_to_zero() -> None:
    observe_sync_lag(event_type="obs.lag.neg", seconds=-5.0)
    total = SYNC_REGISTRY.get_sample_value(
        "posnet_sync_lag_seconds_sum", {"event_type": "obs.lag.neg"}
    )
    assert total == 0.0  # clamped, not negative


@pytest.mark.unit
def test_set_dlq_depth_sets_gauge() -> None:
    set_dlq_depth(queue="obs-dlq", depth=7)
    assert SYNC_REGISTRY.get_sample_value("posnet_sync_dlq_depth", {"queue": "obs-dlq"}) == 7.0


@pytest.mark.unit
def test_render_sync_metrics_emits_exposition_text() -> None:
    record_push(channel_code="obs-render", operation="push_stock", outcome="success")
    body = render_sync_metrics().decode()
    assert "posnet_sync_push_total" in body
    assert "posnet_sync_dlq_depth" in body
    assert "posnet_sync_lag_seconds" in body


# ----------------------------------------------------------------
# collect_dlq_depth — real pgmq queue
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_collect_dlq_depth_reads_pgmq_and_sets_gauge(
    migrated_db: None, async_engine: object
) -> None:
    """Push three messages onto a queue, then ``collect_dlq_depth`` mirrors the
    live pgmq depth into the gauge."""
    from sqlalchemy import text

    from libs.eventbus import pgmq

    queue = "obs_dlq_test"
    async with async_engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgmq"))
        await pgmq.ensure_queue(conn, queue)
        await pgmq.purge(conn, queue)
        for i in range(3):
            await pgmq.send(conn, queue, {"n": i})
        depth = await collect_dlq_depth(conn, queue)

    assert depth == 3
    assert SYNC_REGISTRY.get_sample_value("posnet_sync_dlq_depth", {"queue": queue}) == 3.0
