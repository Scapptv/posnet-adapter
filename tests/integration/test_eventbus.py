"""AI-1.14 — eventbus over real Postgres/pgmq (G1: publish → consume → DLQ).

Connects as the container's superuser (the table owner), which bypasses the
non-FORCED RLS — matching the relay's cross-tenant role requirement (ADR-0013).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from libs.eventbus import Consumer, Event, EventBusConfig, OutboxRelay, enqueue, pgmq

QUEUE = "test_posnet_events"
DLQ = "test_posnet_events_dlq"


def _config(**overrides: object) -> EventBusConfig:
    return EventBusConfig(queue=QUEUE, dlq=DLQ, **overrides)  # type: ignore[arg-type]


@pytest_asyncio.fixture(autouse=True)
async def clean_eventbus(migrated_db: None, async_engine: AsyncEngine) -> AsyncIterator[None]:
    async with async_engine.begin() as conn:
        # The dev stack provisions pgmq via init.sql; testcontainers does not.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgmq"))
        await pgmq.ensure_queue(conn, QUEUE)
        await pgmq.ensure_queue(conn, DLQ)
        await pgmq.purge(conn, QUEUE)
        await pgmq.purge(conn, DLQ)
        await conn.execute(text("TRUNCATE outbox_events"))
    yield


@pytest.mark.integration
async def test_enqueue_persists_unpublished_row(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid4()
    async with async_session_factory() as session, session.begin():
        await enqueue(session, Event(event_type="t", tenant_id=tenant_id, payload={"a": 1}))

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT tenant_id, event_type, payload, published FROM outbox_events")
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].published is False
    assert rows[0].event_type == "t"
    assert rows[0].payload == {"a": 1}
    assert str(rows[0].tenant_id) == str(tenant_id)


@pytest.mark.integration
async def test_relay_publishes_to_pgmq_and_marks_published(
    async_engine: AsyncEngine,
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cfg = _config()
    tenant_id = uuid4()
    async with async_session_factory() as session, session.begin():
        await enqueue(session, Event(event_type="a", tenant_id=tenant_id))
        await enqueue(session, Event(event_type="b", tenant_id=tenant_id))

    relay = OutboxRelay(async_session_factory, cfg)
    assert await relay.run_once() == 2
    assert await relay.run_once() == 0  # nothing left to publish (idempotent)

    async with async_session_factory() as session:
        unpublished = (
            await session.execute(text("SELECT count(*) FROM outbox_events WHERE NOT published"))
        ).scalar_one()
    assert unpublished == 0

    async with async_engine.begin() as conn:
        assert await pgmq.queue_length(conn, QUEUE) == 2


@pytest.mark.integration
async def test_consumer_handles_and_archives(
    async_engine: AsyncEngine,
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cfg = _config()
    tenant_id = uuid4()
    received: list[Event] = []

    async def handler(_session: AsyncSession, event: Event) -> None:
        received.append(event)

    async with async_engine.begin() as conn:
        await pgmq.send(
            conn, QUEUE, Event(event_type="x", tenant_id=tenant_id, payload={"k": 1}).to_message()
        )

    consumer = Consumer(async_session_factory, cfg, handler)
    assert await consumer.run_once() is True
    assert await consumer.run_once() is False  # queue drained

    assert len(received) == 1
    assert received[0].event_type == "x"
    assert received[0].payload == {"k": 1}
    assert received[0].tenant_id == tenant_id

    async with async_engine.begin() as conn:
        assert await pgmq.queue_length(conn, QUEUE) == 0


@pytest.mark.integration
async def test_consumer_retries_then_routes_to_dlq(
    async_engine: AsyncEngine,
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # cap=0 -> set_vt(0) makes a failed message immediately re-readable, so the
    # retry path runs without sleeping on the wall clock.
    cfg = _config(max_retries=3, backoff_cap_seconds=0, visibility_timeout_seconds=1)
    tenant_id = uuid4()
    attempts = 0

    async def failing(_session: AsyncSession, _event: Event) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    async with async_engine.begin() as conn:
        await pgmq.send(conn, QUEUE, Event(event_type="x", tenant_id=tenant_id).to_message())

    consumer = Consumer(async_session_factory, cfg, failing)
    for _ in range(3):  # read_ct 1,2 -> backoff; read_ct 3 -> DLQ
        assert await consumer.run_once() is True

    assert attempts == 3
    async with async_engine.begin() as conn:
        assert await pgmq.queue_length(conn, QUEUE) == 0
        assert await pgmq.queue_length(conn, DLQ) == 1
        dead = await pgmq.read(conn, DLQ, vt_seconds=0, qty=1)
    assert dead[0].message["source_queue"] == QUEUE
    assert dead[0].message["event"]["event_type"] == "x"
    assert "RuntimeError" in dead[0].message["error"]

    assert await consumer.run_once() is False  # no longer deliverable from the main queue


@pytest.mark.integration
async def test_outbox_to_consumer_roundtrip(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cfg = _config()
    tenant_id = uuid4()
    received: list[Event] = []

    async def handler(_session: AsyncSession, event: Event) -> None:
        received.append(event)

    async with async_session_factory() as session, session.begin():
        await enqueue(
            session,
            Event(event_type="catalog.product.created", tenant_id=tenant_id, payload={"sku": "S1"}),
        )

    relay = OutboxRelay(async_session_factory, cfg)
    consumer = Consumer(async_session_factory, cfg, handler)
    assert await relay.run_once() == 1
    assert await consumer.run_once() is True

    assert len(received) == 1
    assert received[0].event_type == "catalog.product.created"
    assert received[0].payload == {"sku": "S1"}
    assert received[0].tenant_id == tenant_id


@pytest.mark.integration
async def test_consumer_runs_without_tenant_context(
    async_engine: AsyncEngine,
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cfg = _config(set_tenant_context=False)
    tenant_id = uuid4()
    received: list[Event] = []

    async def handler(_session: AsyncSession, event: Event) -> None:
        received.append(event)

    async with async_engine.begin() as conn:
        await pgmq.send(conn, QUEUE, Event(event_type="sys", tenant_id=tenant_id).to_message())

    consumer = Consumer(async_session_factory, cfg, handler)
    assert await consumer.run_once() is True
    assert [e.event_type for e in received] == ["sys"]


@pytest.mark.integration
async def test_workers_run_forever_idle_then_process(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cfg = _config(poll_interval_seconds=0.01)
    tenant_id = uuid4()
    received: list[Event] = []
    consumed = asyncio.Event()

    async def handler(_session: AsyncSession, event: Event) -> None:
        received.append(event)
        consumed.set()  # the consumer's stop event — exit after one delivery

    relay = OutboxRelay(async_session_factory, cfg)
    consumer = Consumer(async_session_factory, cfg, handler)
    relay_stop = asyncio.Event()

    relay_task = asyncio.create_task(relay.run_forever(stop=relay_stop))
    consumer_task = asyncio.create_task(consumer.run_forever(stop=consumed))
    await asyncio.sleep(0.05)  # both loops idle on the empty backlog first

    async with async_session_factory() as session, session.begin():
        await enqueue(session, Event(event_type="e", tenant_id=tenant_id))

    await asyncio.wait_for(consumer_task, timeout=5)
    relay_stop.set()
    await asyncio.wait_for(relay_task, timeout=5)
    assert [e.event_type for e in received] == ["e"]
