"""AI-1.9.5 — eventbus config mapping, default handler, disabled lifespan (unit)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from libs.eventbus.event import Event
from services.core.app.config import Settings
from services.core.app.eventbus_workers import (
    _log_if_crashed,
    build_eventbus_config,
    log_event_handler,
)
from services.core.app.main import create_app, lifespan


@pytest.mark.unit
def test_build_eventbus_config_from_settings() -> None:
    cfg = build_eventbus_config(
        Settings(
            pgmq_queue="q",
            pgmq_dlq="d",
            pgmq_visibility_timeout=7,
            pgmq_max_retry=2,
            eventbus_poll_interval_seconds=0.5,
        )
    )
    assert cfg.queue == "q"
    assert cfg.dlq == "d"
    assert cfg.visibility_timeout_seconds == 7
    assert cfg.max_retries == 2
    assert cfg.poll_interval_seconds == 0.5


@pytest.mark.unit
async def test_log_event_handler_runs() -> None:
    # Placeholder handler ignores the session and just logs — must not raise.
    await log_event_handler(None, Event(event_type="t", tenant_id=uuid4()))  # type: ignore[arg-type]


@pytest.mark.unit
async def test_lifespan_skips_workers_when_disabled() -> None:
    app = create_app(
        Settings(
            environment="local",
            database_url="postgresql+psycopg://u@localhost/x",
            redis_url="redis://localhost:6379/0",
            eventbus_enabled=False,
        )
    )
    async with lifespan(app):
        assert app.state.eventbus_workers is None


@pytest.mark.unit
async def test_log_if_crashed_logs_worker_exception() -> None:
    async def _boom() -> None:
        raise RuntimeError("worker died")

    task: asyncio.Task[None] = asyncio.create_task(_boom())
    await asyncio.gather(task, return_exceptions=True)
    _log_if_crashed(task)  # exception path -> logs, must not raise


@pytest.mark.unit
async def test_log_if_crashed_ignores_clean_and_cancelled() -> None:
    async def _ok() -> None:
        return None

    clean: asyncio.Task[None] = asyncio.create_task(_ok())
    await clean
    _log_if_crashed(clean)  # no exception -> no log

    async def _sleep() -> None:
        await asyncio.sleep(10)

    cancelled: asyncio.Task[None] = asyncio.create_task(_sleep())
    cancelled.cancel()
    await asyncio.gather(cancelled, return_exceptions=True)
    _log_if_crashed(cancelled)  # cancelled -> early return
