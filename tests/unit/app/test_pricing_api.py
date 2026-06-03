"""AI-2.3 — pricing request schema (unit, no IO)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from services.core.app.api.v1.pricing import PriceOverrideCreateRequest

_T0 = datetime(2026, 6, 1, tzinfo=UTC)


@pytest.mark.unit
def test_override_request_minimal() -> None:
    req = PriceOverrideCreateRequest(price_minor=1500)
    assert req.store_id is None
    assert req.valid_from is None and req.valid_to is None


@pytest.mark.unit
def test_override_request_open_ended_window_ok() -> None:
    # only one bound set -> window check is skipped
    assert PriceOverrideCreateRequest(price_minor=10, valid_from=_T0).valid_to is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"price_minor": -1},  # negative price
        {"price_minor": 10, "valid_from": _T0, "valid_to": _T0},  # from == to
        {"price_minor": 10, "valid_from": _T0, "valid_to": _T0 - timedelta(days=1)},  # from > to
        {"price_minor": 10, "extra": "x"},  # extra forbidden
    ],
    ids=["negative-price", "window-equal", "window-inverted", "extra-field"],
)
def test_override_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PriceOverrideCreateRequest(**{"price_minor": 100, **overrides})
