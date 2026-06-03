"""AI-2.1 — catalog request schemas (unit, no IO)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from services.core.app.api.v1.catalog import ProductCreateRequest, VariantCreateRequest


@pytest.mark.unit
def test_product_currency_upper_and_default() -> None:
    assert ProductCreateRequest(name="Cola").currency == "AZN"  # default
    assert ProductCreateRequest(name="Cola", currency="try").currency == "TRY"  # upper-cased


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},  # blank name
        {"currency": "azns"},  # 4 chars
        {"currency": "a1z"},  # non-alpha after upper
        {"extra": "x"},  # extra forbidden
    ],
    ids=["blank-name", "currency-too-long", "currency-non-alpha", "extra-field"],
)
def test_product_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ProductCreateRequest(**{"name": "Cola", **overrides})


@pytest.mark.unit
def test_variant_defaults() -> None:
    req = VariantCreateRequest(sku="SKU1", base_price_minor=1500)
    assert req.barcode is None
    assert req.attributes == {}
    assert req.cost_price_minor is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"sku": ""},  # blank sku
        {"base_price_minor": -1},  # negative price
        {"base_price_minor": 0, "cost_price_minor": -5},  # negative cost
        {"base_price_minor": 0, "extra": 1},  # extra forbidden
    ],
    ids=["blank-sku", "negative-price", "negative-cost", "extra-field"],
)
def test_variant_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VariantCreateRequest(**{"sku": "SKU1", "base_price_minor": 100, **overrides})
