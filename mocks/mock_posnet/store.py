"""In-memory state for the HTTP mock Posnet (AI-2.8.2). Pure data, no IO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import CatalogProduct


@dataclass
class MockPosnetStore:
    """Owns the fake POS catalog + the orders the hub has written back."""

    _catalog: list[CatalogProduct] = field(default_factory=list)
    received_orders: list[dict[str, Any]] = field(default_factory=list)
    """Orders the connector pushed (tests assert against this)."""

    def seed(self, *products: CatalogProduct) -> None:
        self._catalog.extend(products)

    def catalog(self) -> list[CatalogProduct]:
        return list(self._catalog)

    def record_order(self, body: dict[str, Any]) -> None:
        self.received_orders.append(body)
