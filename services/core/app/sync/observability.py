"""Sync-engine observability — OTel spans + Prometheus metrics (AI-2.5.6.3).

Roadmap §17.4: "OTel span per sync op (``channel.push``, ``channel.ingest``);
metriklər: sync lag, push success rate, DLQ depth". This module is the one place
that owns those signals so the dispatcher (outbound), the webhook ingress
(inbound) and the reconcile cron all emit a consistent shape.

* **Spans** go through the *global* tracer provider (set by ``setup_telemetry``
  when OTel is enabled). When it isn't, ``trace.get_tracer`` yields a no-op
  tracer, so ``sync_span`` is a cheap nothing — instrument unconditionally.
* **Metrics** live on a dedicated :class:`CollectorRegistry` (``SYNC_REGISTRY``),
  not the app's per-request HTTP registry and not the global default. That keeps
  the dispatcher/cron free to record from anywhere (background task, separate
  process) without import-time coupling to a FastAPI app, and avoids duplicate
  registration across test apps. ``render_sync_metrics`` emits the Prometheus
  exposition text for whoever scrapes/pushes it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.ext.asyncio import AsyncConnection

from libs.eventbus import pgmq

# ----------------------------------------------------------------------------
# Tracing
# ----------------------------------------------------------------------------

_TRACER_NAME = "posnet.sync"


@contextmanager
def sync_span(name: str, **attributes: str | int | bool | None) -> Iterator[Span]:
    """Start a sync-operation span (e.g. ``channel.push`` / ``channel.ingest``).

    ``None`` attribute values are dropped (OTel rejects them). Resolves the
    tracer lazily so a provider installed after import still takes effect.
    """
    tracer = trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------

SYNC_REGISTRY = CollectorRegistry()
"""Dedicated registry for sync-engine metrics (scrape via ``render_sync_metrics``)."""

PUSH_TOTAL = Counter(
    "posnet_sync_push",
    "Outbound channel push operations, labelled by outcome.",
    labelnames=("channel_code", "operation", "outcome"),
    registry=SYNC_REGISTRY,
)
"""``outcome`` ∈ success | breaker_open | retryable | permanent — the success
rate is ``success / sum`` per (channel, operation). Prometheus appends ``_total``,
so the value sample is ``posnet_sync_push_total``."""

DLQ_DEPTH = Gauge(
    "posnet_sync_dlq_depth",
    "Current dead-letter queue depth (messages awaiting operator attention).",
    labelnames=("queue",),
    registry=SYNC_REGISTRY,
)

SYNC_LAG_SECONDS = Histogram(
    "posnet_sync_lag_seconds",
    "Lag from an event's occurrence to the dispatcher processing it.",
    labelnames=("event_type",),
    registry=SYNC_REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


def record_push(*, channel_code: str, operation: str, outcome: str) -> None:
    """Count one outbound push by its outcome (drives the push success rate)."""
    PUSH_TOTAL.labels(channel_code=channel_code, operation=operation, outcome=outcome).inc()


def observe_sync_lag(*, event_type: str, seconds: float) -> None:
    """Record how stale an event was when the dispatcher picked it up."""
    SYNC_LAG_SECONDS.labels(event_type=event_type).observe(max(seconds, 0.0))


def set_dlq_depth(*, queue: str, depth: int) -> None:
    DLQ_DEPTH.labels(queue=queue).set(depth)


async def collect_dlq_depth(conn: AsyncConnection, queue: str) -> int:
    """Read the live DLQ depth via pgmq and publish it to the gauge.

    Meant to be polled (cron / a periodic task) — pgmq's ``metrics`` is the
    source of truth, the gauge is the scrapeable mirror."""
    depth = await pgmq.queue_length(conn, queue)
    set_dlq_depth(queue=queue, depth=depth)
    return depth


def render_sync_metrics() -> bytes:
    """Prometheus exposition text for ``SYNC_REGISTRY`` (text/plain; version=0.0.4)."""
    return generate_latest(SYNC_REGISTRY)
