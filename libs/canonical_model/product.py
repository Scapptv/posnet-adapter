"""Canonical product — the full listing snapshot pushed to a channel (AI-1.4)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from libs.common import Money

from .base import CanonicalBase, CurrencyCode


class ProductStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class CanonicalProduct(CanonicalBase):
    """SKU/barcode-centric product as the hub sees it, regardless of channel."""

    sku: str
    barcode: str | None = None
    name: str
    attributes: dict[str, str] = Field(default_factory=dict)
    category_path: tuple[str, ...] = ()
    price_minor: int
    currency: CurrencyCode
    stock_qty: int
    images: tuple[str, ...] = ()
    status: ProductStatus = ProductStatus.ACTIVE

    @property
    def price(self) -> Money:
        return Money(self.price_minor, self.currency)
