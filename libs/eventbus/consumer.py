"""pgmq consumer with retry/backoff and dead-letter routing (AI-1.14).

Delivery is at-least-once. Each ``run_once``:

1. reads one message (its own committed tx, so the ``read_ct``/visibility bump
   survives a later handler failure — otherwise a poison message would loop
   forever with ``read_ct`` stuck at 1);
2. runs the handler and archives the message in *one* transaction, so a
   successful handle and its ack commit together;
3. on failure, in a separate tx, either reschedules with exponential backoff or
   — once ``read_ct`` reaches ``max_retries`` — moves the message to the DLQ.

Handlers must be idempotent on ``event.event_id``: a crash between the handler
commit and the next read can redeliver a message.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import Event as AsyncEvent
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import pgmq
from .config import EventBusConfig, backoff_seconds
from .event import Event

EventHandler = Callable[[AsyncSession, Event], Awaitable[None]]

_log = logging.getLogger(__name__)

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tid, true)")


class Consumer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: EventBusConfig,
        handler: EventHandler,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._handler = handler

    async def run_once(self) -> bool:
        """Process at most one message; returns ``False`` when the queue is empty."""
        message = await self._read_one()
        if message is None:
            return False

        event = Event.from_message(message.message)
        try:
            async with self._session_factory() as session, session.begin():
                if self._config.set_tenant_context:
                    await session.execute(_SET_TENANT, {"tid": str(event.tenant_id)})
                await self._handler(session, event)
                conn = await session.connection()
                await pgmq.archive(conn, self._config.queue, message.msg_id)
        except Exception as exc:
            # A handler failure is expected control flow — it drives retry/DLQ,
            # not a crash. CancelledError/KeyboardInterrupt are BaseException and
            # propagate.
            await self._on_failure(message, exc)
        return True

    async def _read_one(self) -> pgmq.QueueMessage | None:
        async with self._session_factory() as session, session.begin():
            conn = await session.connection()
            messages = await pgmq.read(
                conn, self._config.queue, self._config.visibility_timeout_seconds, qty=1
            )
        return messages[0] if messages else None

    async def _on_failure(self, message: pgmq.QueueMessage, exc: Exception) -> None:
        async with self._session_factory() as session, session.begin():
            conn = await session.connection()
            if message.read_ct >= self._config.max_retries:
                _log.warning(
                    "event msg_id=%s exhausted %s retries -> DLQ",
                    message.msg_id,
                    self._config.max_retries,
                )
                await pgmq.send(conn, self._config.dlq, self._dlq_envelope(message, exc))
                await pgmq.archive(conn, self._config.queue, message.msg_id)
            else:
                delay = backoff_seconds(
                    message.read_ct,
                    base=self._config.backoff_base_seconds,
                    cap=self._config.backoff_cap_seconds,
                )
                _log.info(
                    "event msg_id=%s failed (attempt %s), retrying in %ss",
                    message.msg_id,
                    message.read_ct,
                    delay,
                )
                await pgmq.set_vt(conn, self._config.queue, message.msg_id, delay)

    def _dlq_envelope(self, message: pgmq.QueueMessage, exc: Exception) -> dict[str, object]:
        return {
            "event": message.message,
            "error": f"{type(exc).__name__}: {exc}",
            "failed_at": datetime.now(UTC).isoformat(),
            "original_msg_id": message.msg_id,
            "read_ct": message.read_ct,
            "source_queue": self._config.queue,
        }

    async def run_forever(self, *, stop: AsyncEvent | None = None) -> None:
        """Consume continuously until ``stop`` is set, idling when the queue is empty."""
        while stop is None or not stop.is_set():
            handled = await self.run_once()
            if not handled:
                await asyncio.sleep(self._config.poll_interval_seconds)
