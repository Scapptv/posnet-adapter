"""Canonical event envelope carried on the bus (AI-1.14).

The same envelope is written to the transactional outbox, relayed onto pgmq and
handed to consumers — so ``to_message``/``from_message`` round-trip losslessly
through JSON (pgmq stores ``jsonb``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Immutable domain event envelope.

    ``event_id`` doubles as the idempotency key for consumers: pgmq delivery is
    at-least-once, so handlers with external side effects must dedupe on it.
    """

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    tenant_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_now)

    def to_message(self) -> dict[str, Any]:
        """Render the JSON-safe wire form stored in pgmq."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "tenant_id": str(self.tenant_id),
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> Event:
        """Parse the wire form produced by :meth:`to_message`."""
        return cls.model_validate(message)
