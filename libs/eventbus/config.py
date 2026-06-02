"""EventBus tuning knobs (AI-1.14).

A plain dataclass, not pydantic-settings: libs stay infrastructure-free
(CLAUDE.md), so the app maps ``EVENTBUS_*`` env → ``EventBusConfig`` when it
wires the workers (AI-1.9).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventBusConfig:
    queue: str = "posnet_events"
    dlq: str = "posnet_events_dlq"
    # Relay: how many outbox rows to drain per transaction.
    batch_size: int = 100
    # Idle backoff for the run_forever loops (seconds).
    poll_interval_seconds: float = 1.0
    # Consumer: how long a read message stays invisible while a handler runs.
    # Must exceed the worst-case handler duration or the message redelivers.
    visibility_timeout_seconds: int = 30
    # Consumer: attempts before a message is routed to the DLQ.
    max_retries: int = 5
    # Consumer: retry delay = min(base ** read_ct, cap) seconds.
    backoff_base_seconds: int = 2
    backoff_cap_seconds: int = 300
    # Consumer: SET LOCAL app.current_tenant from the event before the handler,
    # so RLS scopes the handler's writes to the event's tenant.
    set_tenant_context: bool = True


def backoff_seconds(read_ct: int, *, base: int, cap: int) -> int:
    """Exponential backoff delay for a message read ``read_ct`` times."""
    return min(int(base ** max(read_ct, 1)), cap)
