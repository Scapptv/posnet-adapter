"""Canonical price — a targeted price for push_price (AI-1.4)."""

from __future__ import annotations

from libs.common import Money

from .base import CanonicalBase, CurrencyCode


class CanonicalPrice(CanonicalBase):
    sku: str
    price_minor: int
    currency: CurrencyCode

    @property
    def price(self) -> Money:
        return Money(self.price_minor, self.currency)
