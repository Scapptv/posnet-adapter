"""AI-2.4 — shift/cash request schemas (unit, no IO)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.core.app.api.v1.shifts import (
    CashMovementRequest,
    CloseShiftRequest,
    OpenShiftRequest,
)

_STORE = uuid4()
_CASHIER = uuid4()


@pytest.mark.unit
def test_open_request_currency_upper_and_default() -> None:
    assert (
        OpenShiftRequest(store_id=_STORE, cashier_id=_CASHIER, opening_cash_minor=0).currency
        == "AZN"
    )
    req = OpenShiftRequest(
        store_id=_STORE, cashier_id=_CASHIER, opening_cash_minor=0, currency="try"
    )
    assert req.currency == "TRY"


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [{"opening_cash_minor": -1}, {"opening_cash_minor": 0, "currency": "az"}, {"extra": 1}],
    ids=["negative-cash", "bad-currency", "extra-field"],
)
def test_open_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    base = {"store_id": _STORE, "cashier_id": _CASHIER, "opening_cash_minor": 0}
    with pytest.raises(ValidationError):
        OpenShiftRequest(**{**base, **overrides})


@pytest.mark.unit
def test_close_request_requires_non_negative() -> None:
    assert CloseShiftRequest(closing_cash_minor=500).closing_cash_minor == 500
    with pytest.raises(ValidationError):
        CloseShiftRequest(closing_cash_minor=-1)


@pytest.mark.unit
def test_cash_movement_request_valid() -> None:
    assert CashMovementRequest(kind="in", amount_minor=100).reason is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [{"kind": "deposit"}, {"kind": "in", "amount_minor": 0}, {"kind": "out", "extra": 1}],
    ids=["unknown-kind", "non-positive", "extra-field"],
)
def test_cash_movement_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CashMovementRequest(**{"kind": "in", "amount_minor": 100, **overrides})
