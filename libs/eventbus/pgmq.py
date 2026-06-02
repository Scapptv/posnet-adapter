"""Thin async wrapper over the pgmq SQL functions (AI-1.14).

We call pgmq through SQLAlchemy rather than a standalone asyncpg pool on purpose:
pgmq queues live in the *same* Postgres as the outbox, so a single transaction
can both ``pgmq.send`` and mark the outbox row published — a genuinely atomic
relay with no dual-write window. This module isolates every pgmq query, so a
future broker swap (LOCKED #12: Kafka only on a proven bottleneck) is contained.

Queue names are always passed as bound *arguments* to the pgmq functions (never
interpolated into identifiers), so there is no SQL-injection surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class QueueMessage:
    msg_id: int
    read_ct: int
    enqueued_at: datetime
    vt: datetime
    message: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    # psycopg3 decodes jsonb to a dict; stay robust if a driver returns text.
    if isinstance(value, dict):
        return value
    parsed: dict[str, Any] = orjson.loads(value)
    return parsed


async def ensure_queue(conn: AsyncConnection, queue: str) -> None:
    """Create ``queue`` if it does not already exist (idempotent)."""
    existing = await conn.execute(
        text("SELECT 1 FROM pgmq.list_queues() WHERE queue_name = :q"), {"q": queue}
    )
    if existing.first() is None:
        await conn.execute(text("SELECT pgmq.create(:q)"), {"q": queue})


async def send(conn: AsyncConnection, queue: str, message: dict[str, Any]) -> int:
    result = await conn.execute(
        text("SELECT * FROM pgmq.send(:q, CAST(:m AS jsonb))"),
        {"q": queue, "m": orjson.dumps(message).decode()},
    )
    return int(result.scalar_one())


async def read(
    conn: AsyncConnection, queue: str, vt_seconds: int, qty: int = 1
) -> list[QueueMessage]:
    """Read up to ``qty`` messages, hiding them for ``vt_seconds``."""
    result = await conn.execute(
        text("SELECT msg_id, read_ct, enqueued_at, vt, message FROM pgmq.read(:q, :vt, :qty)"),
        {"q": queue, "vt": vt_seconds, "qty": qty},
    )
    return [
        QueueMessage(
            msg_id=row.msg_id,
            read_ct=row.read_ct,
            enqueued_at=row.enqueued_at,
            vt=row.vt,
            message=_as_dict(row.message),
        )
        for row in result.all()
    ]


async def archive(conn: AsyncConnection, queue: str, msg_id: int) -> bool:
    """Move a message from the queue into its archive table."""
    result = await conn.execute(
        text("SELECT pgmq.archive(:q, CAST(:id AS bigint))"), {"q": queue, "id": msg_id}
    )
    return bool(result.scalar_one())


async def set_vt(conn: AsyncConnection, queue: str, msg_id: int, vt_offset_seconds: int) -> None:
    """Reschedule a message to become visible in ``vt_offset_seconds``."""
    await conn.execute(
        text("SELECT pgmq.set_vt(:q, CAST(:id AS bigint), :vt)"),
        {"q": queue, "id": msg_id, "vt": vt_offset_seconds},
    )


async def purge(conn: AsyncConnection, queue: str) -> int:
    result = await conn.execute(text("SELECT pgmq.purge_queue(:q)"), {"q": queue})
    return int(result.scalar_one())


async def queue_length(conn: AsyncConnection, queue: str) -> int:
    """Number of currently visible + invisible messages in the queue."""
    result = await conn.execute(text("SELECT queue_length FROM pgmq.metrics(:q)"), {"q": queue})
    value = result.scalar_one()
    return int(value) if value is not None else 0
