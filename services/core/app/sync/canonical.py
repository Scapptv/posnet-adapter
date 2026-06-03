"""ORM → CanonicalProduct/Inventory/Price mapper (AI-2.H5, ADR-0018, audit B6).

The hub keeps the source of truth in tenant-scoped ORM rows (Product, Variant,
Inventory[], ResolvedPrice), but every channel adapter speaks the
channel-agnostic canonical model (``libs.canonical_model``). This module is the
bridge.

Two layers:

* **Pure helpers** (``to_canonical_*``, ``aggregate_online_stock``) — no DB
  access, exhaustively testable from in-memory values. Adapter test suites
  rely on these to assert canonical → channel payload mappings without ever
  touching Postgres.
* **Orchestrator** (``build_canonical_product``) — runs against an RLS-scoped
  session, reads everything needed, applies the publish gate, aggregates online
  stock across ``is_online_sellable`` warehouses, and returns the canonical
  snapshot.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.canonical_model import (
    CanonicalInventory,
    CanonicalPrice,
    CanonicalProduct,
    ProductStatus,
)

from ..domain.pricing import resolve_price
from ..infrastructure.db.models import Inventory, Product, ProductImage, Variant, Warehouse

# ----------------------------------------------------------------------------
# Pure helpers (no DB) — test-friendly leaves.
# ----------------------------------------------------------------------------


def aggregate_online_stock(
    inventory_rows: Sequence[Inventory],
    online_sellable_warehouse_ids: set[UUID],
) -> tuple[int, int]:
    """Sum ``(qty, reserved_qty)`` across every inventory row whose warehouse
    is in ``online_sellable_warehouse_ids``.

    Default aggregation per ADR-0018: total stock across online-sellable
    locations, no per-channel buffer, no safety stock. Override mechanisms are
    a future amendment.
    """
    qty = 0
    reserved = 0
    for row in inventory_rows:
        if row.warehouse_id in online_sellable_warehouse_ids:
            qty += row.qty
            reserved += row.reserved_qty
    return qty, reserved


def to_canonical_inventory(*, sku: str, qty: int, reserved_qty: int) -> CanonicalInventory:
    return CanonicalInventory(sku=sku, qty=qty, reserved=reserved_qty)


def to_canonical_price(*, sku: str, price_minor: int, currency: str) -> CanonicalPrice:
    return CanonicalPrice(sku=sku, price_minor=price_minor, currency=currency)


_STATUS_MAP: dict[str, ProductStatus] = {
    "active": ProductStatus.ACTIVE,
    "inactive": ProductStatus.INACTIVE,
    "archived": ProductStatus.ARCHIVED,
}


def to_canonical_product(
    *,
    variant: Variant,
    product: Product,
    image_urls: Sequence[str],
    online_qty: int,
    online_reserved_qty: int,
    effective_price_minor: int,
    currency: str,
) -> CanonicalProduct:
    """Fold every source-of-truth row into one ``CanonicalProduct`` snapshot.

    ``stock_qty`` carries the available (qty - reserved) figure — that's the
    sellable count the adapter pushes to a channel. The non-aggregated row
    counts stay on ``CanonicalInventory`` if a future caller needs them.
    """
    status = _STATUS_MAP.get(product.status, ProductStatus.ACTIVE)
    return CanonicalProduct(
        sku=variant.sku,
        barcode=variant.barcode,
        name=variant.name or product.name,
        attributes=dict(variant.attributes),
        category_path=tuple(product.category_path),
        price_minor=effective_price_minor,
        currency=currency,
        stock_qty=max(online_qty - online_reserved_qty, 0),
        images=tuple(image_urls),
        status=status,
    )


# ----------------------------------------------------------------------------
# Orchestrator — talks to the DB, applies the online-publish gate.
# ----------------------------------------------------------------------------


async def build_canonical_product(
    session: AsyncSession, *, variant_id: UUID, at: datetime
) -> CanonicalProduct | None:
    """Assemble the canonical snapshot for ``variant_id`` at time ``at``.

    Returns ``None`` when the product is not online-published — the publish
    gate (ADR-0018 §2) means an unreleased product is never surfaced to the
    sync engine. Returns ``None`` likewise if the variant doesn't exist in the
    caller's tenant (RLS scope).
    """
    row = (
        await session.execute(
            select(Variant, Product)
            .join(Product, Variant.product_id == Product.id)
            .where(Variant.id == variant_id)
        )
    ).first()
    if row is None:
        return None
    variant, product = row  # SQLAlchemy Row is tuple-unpacking-compatible
    if not product.online_published:
        return None

    inventory_rows: Sequence[Inventory] = (
        (await session.execute(select(Inventory).where(Inventory.variant_id == variant_id)))
        .scalars()
        .all()
    )
    online_warehouse_ids: set[UUID] = set(
        (await session.execute(select(Warehouse.id).where(Warehouse.is_online_sellable.is_(True))))
        .scalars()
        .all()
    )
    online_qty, online_reserved = aggregate_online_stock(inventory_rows, online_warehouse_ids)

    resolved = await resolve_price(session, variant_id=variant_id, at=at)

    image_urls: list[str] = list(
        (
            await session.execute(
                select(ProductImage.url)
                .where(ProductImage.product_id == product.id)
                .order_by(ProductImage.sort_order)
            )
        )
        .scalars()
        .all()
    )

    return to_canonical_product(
        variant=variant,
        product=product,
        image_urls=image_urls,
        online_qty=online_qty,
        online_reserved_qty=online_reserved,
        effective_price_minor=resolved.effective_price_minor,
        currency=resolved.currency,
    )
