"""Posnet canonical model (AI-1.4) — channel-agnostic, immutable v1 schemas.

The hub's single source of truth: every channel adapter maps to and from these.
``CanonicalProduct`` is the full listing snapshot (push_listing); ``CanonicalInventory``
and ``CanonicalPrice`` are targeted updates (push_stock / push_price);
``CanonicalOrder`` is a normalized inbound order (channel -> POS).
"""

from __future__ import annotations

from .base import CanonicalBase, CurrencyCode
from .inventory import CanonicalInventory
from .order import (
    CanonicalCustomer,
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalTotals,
    OrderStatus,
)
from .price import CanonicalPrice
from .product import CanonicalProduct, ProductStatus

__all__ = [
    "CanonicalBase",
    "CanonicalCustomer",
    "CanonicalInventory",
    "CanonicalOrder",
    "CanonicalOrderLine",
    "CanonicalPrice",
    "CanonicalProduct",
    "CanonicalTotals",
    "CurrencyCode",
    "OrderStatus",
    "ProductStatus",
]
