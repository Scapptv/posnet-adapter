"""In-memory mock Posnet POS source (AI-2.8, ADR-0021).

Stands in for the real Posnet ERP so the POS-side integration (catalog pull +
order write-back) can be built and tested before the real interface
(API/DB/format + auth) is known — exactly the mock-first approach the marketplace
adapter used. The real connector swaps in for this on the same
``PosSourceAdapter`` contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from libs.canonical_model import CanonicalOrder, CanonicalProduct
from libs.pos_source import PosSourceCapabilities


@dataclass
class MockPosnetSource:
    """A fake Posnet: seed it with canonical products, read them back, and record
    any orders the hub writes back. One instance per test (fresh world)."""

    capabilities: ClassVar[PosSourceCapabilities] = PosSourceCapabilities(
        code="posnet",
        name="Mock Posnet",
        supports_pull_catalog=True,
        supports_push_order=True,
    )

    _catalog: list[CanonicalProduct] = field(default_factory=list)
    pushed_orders: list[CanonicalOrder] = field(default_factory=list)
    """Channel orders the hub wrote back (tests assert against this)."""

    def seed(self, *products: CanonicalProduct) -> None:
        """Add products to the fake POS catalog."""
        self._catalog.extend(products)

    async def pull_catalog(self) -> Sequence[CanonicalProduct]:
        return list(self._catalog)

    async def push_order(self, order: CanonicalOrder) -> None:
        self.pushed_orders.append(order)
