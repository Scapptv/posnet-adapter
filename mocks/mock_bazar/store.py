"""In-memory state for Mock Bazar (Part V V1.1). Pure data, no IO. One per test."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from .models import Sale, SaleBuyer, SaleItem, SaleTotals


@dataclass
class _Product:
    ref: str
    merchant_sku: str
    gtin: str | None
    title: str
    attrs: dict[str, str]
    category_path: list[str]
    amount_minor: int
    currency: str
    quantity: int
    state: str = "live"


@dataclass
class MockBazarStore:
    """Owns every fact Mock Bazar made up."""

    _products_by_ref: dict[str, _Product] = field(default_factory=dict)
    _products_by_sku: dict[str, _Product] = field(default_factory=dict)
    _sales: list[Sale] = field(default_factory=list)
    _states: dict[str, str] = field(default_factory=dict)
    """``ref`` → last acknowledged sale state."""

    def upsert_product(
        self,
        *,
        merchant_sku: str,
        gtin: str | None,
        title: str,
        attrs: dict[str, str],
        category_path: list[str],
        amount_minor: int,
        currency: str,
        quantity: int,
    ) -> _Product:
        """Idempotent upsert by ``merchant_sku`` (so push_listing can run twice)."""
        existing = self._products_by_sku.get(merchant_sku)
        if existing is not None:
            existing.gtin = gtin
            existing.title = title
            existing.attrs = dict(attrs)
            existing.category_path = list(category_path)
            existing.amount_minor = amount_minor
            existing.currency = currency
            existing.quantity = quantity
            return existing

        ref = f"BZR-{uuid4().hex[:12].upper()}"
        product = _Product(
            ref=ref,
            merchant_sku=merchant_sku,
            gtin=gtin,
            title=title,
            attrs=dict(attrs),
            category_path=list(category_path),
            amount_minor=amount_minor,
            currency=currency,
            quantity=quantity,
        )
        self._products_by_ref[ref] = product
        self._products_by_sku[merchant_sku] = product
        return product

    def set_quantity(self, *, merchant_sku: str, quantity: int) -> _Product | None:
        product = self._products_by_sku.get(merchant_sku)
        if product is None:
            return None
        product.quantity = quantity
        return product

    def set_price(self, *, merchant_sku: str, amount_minor: int, currency: str) -> _Product | None:
        product = self._products_by_sku.get(merchant_sku)
        if product is None:
            return None
        product.amount_minor = amount_minor
        product.currency = currency
        return product

    def seed_sale(self, *, items: list[SaleItem], currency: str, buyer_name: str | None) -> Sale:
        total = sum(item.unit_amount_minor * item.units for item in items)
        sale = Sale(
            ref=f"BZR-SALE-{uuid4().hex[:10].upper()}",
            placed_at=datetime.now(UTC),
            items=list(items),
            totals=SaleTotals(sub_amount_minor=total, grand_amount_minor=total, currency=currency),
            buyer=SaleBuyer(name=buyer_name),
            state="new",
        )
        self._sales.append(sale)
        return sale

    def sales_since(self, since: datetime) -> list[Sale]:
        return [sale for sale in self._sales if sale.placed_at >= since]

    def set_sale_state(self, *, ref: str, state: str) -> bool:
        for sale in self._sales:
            if sale.ref == ref:
                self._states[ref] = state
                sale.state = state  # type: ignore[assignment]
                return True
        return False

    # ---- read-only views (tests poke these) ----

    def product_by_sku(self, merchant_sku: str) -> _Product | None:
        return self._products_by_sku.get(merchant_sku)

    def last_state(self, ref: str) -> str | None:
        return self._states.get(ref)
