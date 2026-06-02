"""Canonical order — a channel order normalized for ingest into POS (AI-1.4).

Inbound flow: channel webhook -> adapter.normalize -> CanonicalOrder -> Order
context -> POS stock decrement. The lines carry the SKU/qty the hub decrements.
"""

from __future__ import annotations

from enum import StrEnum

from libs.common import Money

from .base import CanonicalBase, CurrencyCode


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class CanonicalCustomer(CanonicalBase):
    name: str
    email: str | None = None
    phone: str | None = None


class CanonicalOrderLine(CanonicalBase):
    sku: str
    name: str
    qty: int
    unit_price_minor: int
    currency: CurrencyCode

    @property
    def unit_price(self) -> Money:
        return Money(self.unit_price_minor, self.currency)


class CanonicalTotals(CanonicalBase):
    subtotal_minor: int
    grand_total_minor: int
    currency: CurrencyCode
    shipping_minor: int = 0
    tax_minor: int = 0

    @property
    def grand_total(self) -> Money:
        return Money(self.grand_total_minor, self.currency)


class CanonicalOrder(CanonicalBase):
    channel_order_id: str
    lines: tuple[CanonicalOrderLine, ...]
    totals: CanonicalTotals
    status: OrderStatus = OrderStatus.PENDING
    customer: CanonicalCustomer | None = None
    fulfillment: str | None = None
