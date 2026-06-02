"""Transactional outbox write (AI-1.14).

Domain code calls :func:`enqueue` inside its *own* business transaction, so the
event row and the business change commit (or roll back) together. The relay
later turns unpublished rows into pgmq messages.

The ``outbox_events`` table is owned by migration 0001 (services/core); this
library targets it by column contract via ``text()`` and never imports the ORM
model, keeping ``libs/`` free of a dependency on a concrete service.
"""

from __future__ import annotations

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .event import Event

_INSERT = text(
    """
    INSERT INTO outbox_events (id, tenant_id, event_type, payload, published, created_at)
    VALUES (:id, :tenant_id, :event_type, CAST(:payload AS jsonb), false, :occurred_at)
    """
)


async def enqueue(session: AsyncSession, event: Event) -> None:
    """Persist ``event`` in the outbox within the caller's transaction.

    Does not commit — the caller owns the transaction boundary so the event is
    atomic with the business write that produced it.
    """
    await session.execute(
        _INSERT,
        {
            "id": event.event_id,
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "payload": orjson.dumps(event.payload).decode(),
            "occurred_at": event.occurred_at,
        },
    )
