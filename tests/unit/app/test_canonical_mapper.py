"""AI-2.H5 — canonical mapper pure helpers (audit B6).

The pure helpers are the seam adapter test suites lean on: they take in-memory
ORM-shaped values and return canonical schemas, with no DB access. Test them
exhaustively here so adapter tests (AI-2.5) can take their correctness as given.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from libs.canonical_model import ProductStatus
from services.core.app.sync.canonical import (
    aggregate_online_stock,
    to_canonical_inventory,
    to_canonical_price,
    to_canonical_product,
)

# ----------------------------------------------------------------------------
# aggregate_online_stock
# ----------------------------------------------------------------------------


def _inv(warehouse_id: Any, qty: int, reserved_qty: int) -> SimpleNamespace:
    """Stand-in for an Inventory row — the aggregator only reads three fields."""
    return SimpleNamespace(warehouse_id=warehouse_id, qty=qty, reserved_qty=reserved_qty)


@pytest.mark.unit
def test_aggregate_online_stock_empty_rows() -> None:
    assert aggregate_online_stock([], set()) == (0, 0)


@pytest.mark.unit
def test_aggregate_online_stock_sums_only_sellable_warehouses() -> None:
    """Non-sellable rows (showroom / B2B) are excluded from the online figure."""
    online_a, online_b, b2b = uuid4(), uuid4(), uuid4()
    rows = [
        _inv(online_a, qty=10, reserved_qty=2),
        _inv(online_b, qty=5, reserved_qty=1),
        _inv(b2b, qty=100, reserved_qty=20),  # showroom; not counted
    ]
    qty, reserved = aggregate_online_stock(rows, {online_a, online_b})
    assert qty == 15
    assert reserved == 3


@pytest.mark.unit
def test_aggregate_online_stock_with_no_sellable_warehouses_returns_zero() -> None:
    """All-B2B inventory means zero online stock — there's nothing to sell."""
    b2b = uuid4()
    rows = [_inv(b2b, qty=100, reserved_qty=10)]
    assert aggregate_online_stock(rows, set()) == (0, 0)


# ----------------------------------------------------------------------------
# to_canonical_inventory / to_canonical_price
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_to_canonical_inventory_carries_sku_and_available() -> None:
    inv = to_canonical_inventory(sku="X-1", qty=10, reserved_qty=4)
    assert inv.sku == "X-1"
    assert inv.qty == 10
    assert inv.reserved == 4
    assert inv.available == 6


@pytest.mark.unit
def test_to_canonical_price_carries_money_view() -> None:
    price = to_canonical_price(sku="X-1", price_minor=12345, currency="AZN")
    assert price.sku == "X-1"
    assert price.price_minor == 12345
    assert price.currency == "AZN"
    assert price.price.minor == 12345


# ----------------------------------------------------------------------------
# to_canonical_product
# ----------------------------------------------------------------------------


def _product(**overrides: Any) -> SimpleNamespace:
    base = {
        "name": "Coca Cola",
        "category_path": ["Drinks", "Soda"],
        "status": "active",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _variant(**overrides: Any) -> SimpleNamespace:
    base = {
        "sku": "CC-500",
        "barcode": "8690000000001",
        "name": "Coca Cola 500ml",
        "attributes": {"volume": "500ml"},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.unit
def test_to_canonical_product_uses_variant_name_when_set() -> None:
    canonical = to_canonical_product(
        variant=_variant(name="500ml Bottle"),
        product=_product(),
        image_urls=["http://img/a.png"],
        online_qty=10,
        online_reserved_qty=3,
        effective_price_minor=300,
        currency="AZN",
    )
    assert canonical.name == "500ml Bottle"  # variant beats product
    assert canonical.sku == "CC-500"
    assert canonical.stock_qty == 7  # available = qty - reserved
    assert canonical.images == ("http://img/a.png",)
    assert canonical.category_path == ("Drinks", "Soda")
    assert canonical.price_minor == 300


@pytest.mark.unit
def test_to_canonical_product_falls_back_to_product_name_when_variant_name_blank() -> None:
    canonical = to_canonical_product(
        variant=_variant(name=None),
        product=_product(name="Coca Cola"),
        image_urls=[],
        online_qty=0,
        online_reserved_qty=0,
        effective_price_minor=300,
        currency="AZN",
    )
    assert canonical.name == "Coca Cola"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        ("active", ProductStatus.ACTIVE),
        ("inactive", ProductStatus.INACTIVE),
        ("archived", ProductStatus.ARCHIVED),
        ("unknown-future-value", ProductStatus.ACTIVE),  # safe default
    ],
)
def test_to_canonical_product_status_mapping(source_status: str, expected: ProductStatus) -> None:
    canonical = to_canonical_product(
        variant=_variant(),
        product=_product(status=source_status),
        image_urls=[],
        online_qty=1,
        online_reserved_qty=0,
        effective_price_minor=100,
        currency="AZN",
    )
    assert canonical.status == expected


@pytest.mark.unit
def test_to_canonical_product_stock_qty_never_negative() -> None:
    """If reservations somehow exceed qty (e.g. a stale read), the canonical
    snapshot still clips to zero — the channel must never see a negative
    sellable figure (the anti-oversell guarantee at the canonical layer)."""
    canonical = to_canonical_product(
        variant=_variant(),
        product=_product(),
        image_urls=[],
        online_qty=2,
        online_reserved_qty=5,  # nonsense state, but be defensive
        effective_price_minor=100,
        currency="AZN",
    )
    assert canonical.stock_qty == 0


@pytest.mark.unit
def test_to_canonical_product_passes_variant_attributes_through() -> None:
    canonical = to_canonical_product(
        variant=_variant(attributes={"color": "red", "size": "L"}),
        product=_product(),
        image_urls=[],
        online_qty=1,
        online_reserved_qty=0,
        effective_price_minor=100,
        currency="AZN",
    )
    assert canonical.attributes == {"color": "red", "size": "L"}
