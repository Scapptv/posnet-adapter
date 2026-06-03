"""Consume-side idempotency wrapper (AI-2.H4, audit B5).

pgmq delivery is at-least-once: a crash between the handler commit and the
queue archive will redeliver the same ``event_id``. Handlers with external
side effects (channel adapter pushes, fiscal printer commands) must therefore
dedupe on it.

``idempotent`` wraps an :class:`EventHandler` so the consumer transaction first
tries to insert ``(event_id, tenant_id)`` into ``idempotency_keys``. On a
``ON CONFLICT DO NOTHING`` no-op the row already exists — the handler has
already run, so we skip it; the consumer still archives the redelivery.
Otherwise we run the handler in the same transaction, so the insert and the
side effect commit together: a handler failure rolls back the insert too,
leaving the next redelivery free to retry.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from libs.eventbus import Event, EventHandler

# ON CONFLICT DO NOTHING — the (key) PK collision means the event has been
# handled. ``rowcount == 0`` is the dedupe signal. Insert as the owner session
# (the consumer's session_factory is RLS-exempt), so no per-tenant scope is
# needed before the call.
_INSERT_IDEMPOTENCY_KEY = text(
    """
    INSERT INTO idempotency_keys (key, tenant_id, result_ref)
    VALUES (:key, :tenant_id, :result_ref)
    ON CONFLICT (key) DO NOTHING
    """
)


def idempotent(handler: EventHandler) -> EventHandler:
    """Return a wrapper that runs ``handler`` only on the first delivery of
    ``event.event_id``."""

    async def wrapped(session: AsyncSession, event: Event) -> None:
        # DML statements return a CursorResult; ``rowcount`` lives there, not on
        # the generic ``Result`` type SQLAlchemy stubs declare for execute().
        result = cast(
            CursorResult[object],
            await session.execute(
                _INSERT_IDEMPOTENCY_KEY,
                {
                    "key": str(event.event_id),
                    "tenant_id": event.tenant_id,
                    "result_ref": f"event:{event.event_type}",
                },
            ),
        )
        if result.rowcount == 0:
            return  # already processed; the consumer archives the redelivery
        await handler(session, event)

    return wrapped
