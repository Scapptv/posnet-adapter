"""AI-1.9.5 — eventbus relay/consumer started in the app lifespan.

Drives the real ``lifespan``: it ensures the queue, starts the relay + consumer
on the owner (RLS-exempt) session factory, and stops them on exit. Enqueuing for
two tenants proves the workers are cross-tenant (a tenant-scoped role would see
neither row under RLS).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from libs.eventbus import Event, enqueue, pgmq
from services.core.app.config import Settings
from services.core.app.main import create_app, lifespan

_QUEUE = "posnet_events"


@pytest.mark.integration
async def test_lifespan_starts_workers_and_processes_across_tenants(
    migrated_db: None,
    async_engine: AsyncEngine,
    pg_sqlalchemy_url: str,
    redis_url: str,
) -> None:
    # pgmq comes from the dev stack's init.sql, not migrations/the bare image.
    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgmq"))
        await pgmq.ensure_queue(conn, _QUEUE)
        await pgmq.purge(conn, _QUEUE)
        await conn.execute(text("TRUNCATE outbox_events"))

    received: list[Event] = []
    done = asyncio.Event()

    async def handler(_session: AsyncSession, event: Event) -> None:
        received.append(event)
        if len(received) >= 2:
            done.set()

    app = create_app(
        Settings(
            environment="local",
            database_url=pg_sqlalchemy_url,
            redis_url=redis_url,
            eventbus_enabled=True,
            eventbus_poll_interval_seconds=0.05,
            rate_limit_storage_uri="memory://",
        ),
        event_handler=handler,
    )

    async with lifespan(app):
        workers = app.state.eventbus_workers
        assert workers is not None
        assert workers.running  # relay + consumer tasks live

        t1, t2 = uuid4(), uuid4()
        async with app.state.sessionmaker() as session, session.begin():
            await enqueue(session, Event(event_type="a", tenant_id=t1))
            await enqueue(session, Event(event_type="b", tenant_id=t2))

        await asyncio.wait_for(done.wait(), timeout=15)

    assert not app.state.eventbus_workers.running  # stopped on lifespan exit
    assert {e.tenant_id for e in received} == {t1, t2}  # both tenants processed
