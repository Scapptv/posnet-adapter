"""AI-1.4 — CanonicalPrice: Money bridge + currency contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.canonical_model import CanonicalPrice
from libs.common import Money


@pytest.mark.unit
def test_price_property_returns_money() -> None:
    price = CanonicalPrice(sku="S", price_minor=5000, currency="TRY")
    assert price.price == Money(5000, "TRY")


@pytest.mark.unit
def test_invalid_currency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalPrice(sku="S", price_minor=1, currency="EURO")
