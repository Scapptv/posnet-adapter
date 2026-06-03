"""EventBus worker lifecycle in the app (AI-1.9.5).

Starts the outbox relay and the consumer as background tasks for the app's
lifetime. They run on the app's owner DB session factory, which is RLS-exempt —
exactly the cross-tenant role the relay/consumer need to see every tenant's
``outbox_events`` (ADR-0013; the per-request path instead switches into the
tenant-scoped ``posnet_app`` role). ``EVENTBUS_ENABLED`` gates startup.

The default handler is a placeholder that just logs: foundation produces no
domain events yet. AI-2 injects a real dispatcher via ``create_app(event_handler=...)``.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from libs.eventbus import Consumer, EventBusConfig, EventHandler, OutboxRelay, pgmq
from libs.eventbus.event import Event

from .config import Settings
from .logging_config import get_logger

_log = get_logger("posnet.eventbus")


def build_eventbus_config(settings: Settings) -> EventBusConfig:
    return EventBusConfig(
        queue=settings.pgmq_queue,
        dlq=settings.pgmq_dlq,
        visibility_timeout_seconds=settings.pgmq_visibility_timeout,
        max_retries=settings.pgmq_max_retry,
        poll_interval_seconds=settings.eventbus_poll_interval_seconds,
    )


async def log_event_handler(_session: AsyncSession, event: Event) -> None:
    """Placeholder consumer handler — logs and acks (AI-2 replaces it)."""
    _log.info("event_consumed", event_type=event.event_type, event_id=str(event.event_id))


class EventBusWorkers:
    """Owns the relay + consumer background tasks for the app lifespan."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: EventBusConfig,
        handler: EventHandler,
    ) -> None:
        self._relay = OutboxRelay(session_factory, config)
        self._consumer = Consumer(session_factory, config, handler)
        self._config = config
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def ensure_queues(self, engine: AsyncEngine) -> None:
        """Create the queue + DLQ if missing (idempotent). Runs before start()."""
        async with engine.begin() as conn:
            await pgmq.ensure_queue(conn, self._config.queue)
            await pgmq.ensure_queue(conn, self._config.dlq)

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._relay.run_forever(stop=self._stop), name="eventbus-relay"),
            asyncio.create_task(
                self._consumer.run_forever(stop=self._stop), name="eventbus-consumer"
            ),
        ]
        for task in self._tasks:
            task.add_done_callback(_log_if_crashed)

    @property
    def running(self) -> bool:
        return any(not task.done() for task in self._tasks)

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []


def _log_if_crashed(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _log.error("eventbus_worker_crashed", worker=task.get_name(), exc_info=exc)
