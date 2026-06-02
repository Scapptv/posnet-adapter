"""Posnet event bus — transactional outbox over pgmq (AI-1.14).

The hub's backbone: domain code calls :func:`enqueue` inside its business
transaction; :class:`OutboxRelay` atomically publishes outbox rows to pgmq;
:class:`Consumer` delivers them with retry/backoff and dead-letter routing.
"""

from __future__ import annotations

from . import pgmq
from .config import EventBusConfig, backoff_seconds
from .consumer import Consumer, EventHandler
from .event import Event
from .outbox import enqueue
from .pgmq import QueueMessage
from .relay import OutboxRelay

__all__ = [
    "Consumer",
    "Event",
    "EventBusConfig",
    "EventHandler",
    "OutboxRelay",
    "QueueMessage",
    "backoff_seconds",
    "enqueue",
    "pgmq",
]
