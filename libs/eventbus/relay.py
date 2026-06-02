"""Outbox → pgmq relay worker (AI-1.14).

Each ``run_once`` drains a batch of unpublished outbox rows and, in a single
transaction, sends them to pgmq *and* marks them published. Because pgmq lives
in the same Postgres, that is one local transaction — atomic, with no
dual-write window: a crash either commits both effects or neither.

``FOR UPDATE SKIP LOCKED`` lets several relay workers run concurrently without
publishing a row twice.

Role note: the relay processes *all* tenants' rows, so its DB role must bypass
the per-tenant RLS on ``outbox_events`` (the table owner, or a dedicated
``BYPASSRLS`` role). The per-request :func:`outbox.enqueue` runs under the
tenant-scoped ``posnet_app`` role, where RLS's ``WITH CHECK`` is the
defense-in-depth that stops one tenant enqueuing for another. See ADR-0013.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import Event as AsyncEvent
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import pgmq
from .config import EventBusConfig

_log = logging.getLogger(__name__)

_SELECT_BATCH = text(
    """
    SELECT id, tenant_id, event_type, payload, created_at
    FROM outbox_events
    WHERE NOT published
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch
    """
)

_MARK_PUBLISHED = text("UPDATE outbox_events SET published = true WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)


def _to_envelope(row: Row[Any]) -> dict[str, Any]:
    return {
        "event_id": str(row.id),
        "event_type": row.event_type,
        "tenant_id": str(row.tenant_id),
        "occurred_at": row.created_at.isoformat(),
        "payload": pgmq._as_dict(row.payload),
    }


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: EventBusConfig,
    ) -> None:
        self._session_factory = session_factory
        self._config = config

    async def run_once(self) -> int:
        """Relay one batch; returns how many events were published."""
        async with self._session_factory() as session, session.begin():
            conn = await session.connection()
            rows = (await session.execute(_SELECT_BATCH, {"batch": self._config.batch_size})).all()
            if not rows:
                return 0
            for row in rows:
                await pgmq.send(conn, self._config.queue, _to_envelope(row))
            await session.execute(_MARK_PUBLISHED, {"ids": [row.id for row in rows]})
            return len(rows)

    async def run_forever(self, *, stop: AsyncEvent | None = None) -> None:
        """Relay continuously until ``stop`` is set, idling when the outbox drains."""
        while stop is None or not stop.is_set():
            published = await self.run_once()
            if published == 0:
                await asyncio.sleep(self._config.poll_interval_seconds)
