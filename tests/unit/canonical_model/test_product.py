"""AI-1.4 — CanonicalProduct: defaults, status, Money bridge, currency contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.canonical_model import CanonicalProduct, ProductStatus
from libs.common import Money


@pytest.mark.unit
def test_minimal_product_defaults() -> None:
    product = CanonicalProduct(
        sku="SKU1", name="Phone", price_minor=199900, currency="AZN", stock_qty=10
    )
    assert product.barcode is None
    assert product.attributes == {}
    assert product.category_path == ()
    assert product.images == ()
    assert product.status is ProductStatus.ACTIVE


@pytest.mark.unit
def test_price_property_returns_money() -> None:
    product = CanonicalProduct(sku="S", name="N", price_minor=12345, currency="AZN", stock_qty=1)
    assert product.price == Money(12345, "AZN")
    assert str(product.price) == "123.45 AZN"


@pytest.mark.unit
def test_status_coerces_from_wire_value() -> None:
    product = CanonicalProduct(
        sku="S", name="N", price_minor=1, currency="AZN", stock_qty=1, status="archived"
    )
    assert product.status is ProductStatus.ARCHIVED


@pytest.mark.unit
def test_invalid_currency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalProduct(sku="S", name="N", price_minor=1, currency="azn", stock_qty=1)
