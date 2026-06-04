"""In-memory state for the mock marketplace (AI-2.5.3).

Pure data — no DB, no IO. The mock service is supposed to be cheap to spin up
in tests; persistence would be a distraction. Each :class:`MockStore` is a
fresh world (one per test fixture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from .models import OrderDTO, OrderLineDTO


@dataclass
class _Listing:
    external_id: str
    seller_sku: str
    name: str
    barcode: str | None
    attributes: dict[str, str]
    category: str | None
    price_minor: int
    currency: str
    stock: int
    status: str = "active"


@dataclass
class MockStore:
    """Owns every fact the mock service ever made up."""

    _listings_by_external: dict[str, _Listing] = field(default_factory=dict)
    _listings_by_sku: dict[str, _Listing] = field(default_factory=dict)
    _orders: list[OrderDTO] = field(default_factory=list)
    _acks: dict[str, str] = field(default_factory=dict)
    """``channel_order_id`` → last acknowledged status."""

    def upsert_listing(
        self,
        *,
        seller_sku: str,
        barcode: str | None,
        name: str,
        attributes: dict[str, str],
        category: str | None,
        price_minor: int,
        currency: str,
        stock: int,
    ) -> _Listing:
        """Idempotent upsert by ``seller_sku`` — re-pushing the same listing
        updates fields in place rather than creating a duplicate (so the
        adapter contract test can call ``push_listing`` twice without leaking
        state)."""
        existing = self._listings_by_sku.get(seller_sku)
        if existing is not None:
            existing.barcode = barcode
            existing.name = name
            existing.attributes = dict(attributes)
            existing.category = category
            existing.price_minor = price_minor
            existing.currency = currency
            existing.stock = stock
            return existing

        external_id = f"MOCK-{uuid4().hex[:12].upper()}"
        listing = _Listing(
            external_id=external_id,
            seller_sku=seller_sku,
            name=name,
            barcode=barcode,
            attributes=dict(attributes),
            category=category,
            price_minor=price_minor,
            currency=currency,
            stock=stock,
        )
        self._listings_by_external[external_id] = listing
        self._listings_by_sku[seller_sku] = listing
        return listing

    def set_stock(self, *, seller_sku: str, qty: int) -> _Listing | None:
        listing = self._listings_by_sku.get(seller_sku)
        if listing is None:
            return None
        listing.stock = qty
        return listing

    def set_price(self, *, seller_sku: str, price_minor: int, currency: str) -> _Listing | None:
        listing = self._listings_by_sku.get(seller_sku)
        if listing is None:
            return None
        listing.price_minor = price_minor
        listing.currency = currency
        return listing

    def seed_order(
        self, *, lines: list[OrderLineDTO], currency: str, customer_name: str | None
    ) -> OrderDTO:
        order = OrderDTO(
            channel_order_id=f"MOCK-ORD-{uuid4().hex[:10].upper()}",
            created_at=datetime.now(UTC),
            currency=currency,
            lines=list(lines),
            subtotal_minor=sum(line.unit_price_minor * line.qty for line in lines),
            grand_total_minor=sum(line.unit_price_minor * line.qty for line in lines),
            customer_name=customer_name,
            status="pending",
        )
        self._orders.append(order)
        return order

    def orders_since(self, since: datetime) -> list[OrderDTO]:
        return [order for order in self._orders if order.created_at >= since]

    def acknowledge(self, *, channel_order_id: str, status: str) -> bool:
        for order in self._orders:
            if order.channel_order_id == channel_order_id:
                self._acks[channel_order_id] = status
                order.status = status  # type: ignore[assignment]
                return True
        return False

    # ---- read-only views (tests poke these) ----

    def listing_by_sku(self, seller_sku: str) -> _Listing | None:
        return self._listings_by_sku.get(seller_sku)

    def listing_by_external_id(self, external_id: str) -> _Listing | None:
        return self._listings_by_external.get(external_id)

    def last_ack(self, channel_order_id: str) -> str | None:
        return self._acks.get(channel_order_id)
