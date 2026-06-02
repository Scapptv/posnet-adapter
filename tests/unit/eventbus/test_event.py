"""AI-1.14 — Event envelope: lossless wire round-trip, frozen, sane defaults."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from libs.eventbus import Event


@pytest.mark.unit
def test_defaults_generate_id_and_timestamp() -> None:
    event = Event(event_type="catalog.product.created", tenant_id=uuid4())
    assert isinstance(event.event_id, UUID)
    assert event.occurred_at.tzinfo is not None
    assert event.payload == {}


@pytest.mark.unit
def test_event_is_frozen() -> None:
    event = Event(event_type="t", tenant_id=uuid4())
    with pytest.raises(PydanticValidationError):
        event.event_type = "changed"  # type: ignore[misc]


@pytest.mark.unit
def test_to_message_is_json_safe() -> None:
    event = Event(event_type="t", tenant_id=uuid4(), payload={"sku": "ABC", "qty": 3})
    message = event.to_message()
    assert message["event_id"] == str(event.event_id)
    assert message["tenant_id"] == str(event.tenant_id)
    assert isinstance(message["occurred_at"], str)
    assert message["payload"] == {"sku": "ABC", "qty": 3}


@pytest.mark.unit
def test_round_trip_through_message() -> None:
    original = Event(
        event_id=uuid4(),
        event_type="inventory.stock.adjusted",
        tenant_id=uuid4(),
        payload={"delta": -2},
        occurred_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
    )
    restored = Event.from_message(original.to_message())
    assert restored == original
