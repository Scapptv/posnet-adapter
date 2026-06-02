"""AI-1.4 — CanonicalOrder: nested lines/totals, defaults, frozen, JSON round-trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.canonical_model import (
    CanonicalCustomer,
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalTotals,
    OrderStatus,
)
from libs.common import Money


def _line() -> CanonicalOrderLine:
    return CanonicalOrderLine(sku="S1", name="Item", qty=2, unit_price_minor=1500, currency="AZN")


@pytest.mark.unit
def test_order_defaults_and_money_bridges() -> None:
    order = CanonicalOrder(
        channel_order_id="BM-1",
        lines=(_line(),),
        totals=CanonicalTotals(
            subtotal_minor=3000, grand_total_minor=3500, currency="AZN", shipping_minor=500
        ),
    )
    assert order.status is OrderStatus.PENDING
    assert order.customer is None
    assert order.lines[0].unit_price == Money(1500, "AZN")
    assert order.totals.grand_total == Money(3500, "AZN")


@pytest.mark.unit
def test_order_is_frozen() -> None:
    order = CanonicalOrder(
        channel_order_id="BM-1",
        lines=(_line(),),
        totals=CanonicalTotals(subtotal_minor=3000, grand_total_minor=3000, currency="AZN"),
    )
    with pytest.raises(ValidationError):
        order.status = OrderStatus.FULFILLED  # type: ignore[misc]


@pytest.mark.unit
def test_order_json_round_trip() -> None:
    order = CanonicalOrder(
        channel_order_id="BM-2",
        lines=(_line(),),
        totals=CanonicalTotals(subtotal_minor=3000, grand_total_minor=3000, currency="AZN"),
        customer=CanonicalCustomer(name="Ali", email="ali@example.com"),
        status=OrderStatus.CONFIRMED,
    )
    restored = CanonicalOrder.model_validate(order.model_dump(mode="json"))
    assert restored == order
