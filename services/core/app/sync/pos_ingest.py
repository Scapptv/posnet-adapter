"""POS-side catalog ingest (AI-2.8, ADR-0021).

The inbound mirror of the channel dispatcher: instead of pushing the hub's
catalog *out* to a marketplace, this pulls the source POS (Posnet)'s catalog
*in* and projects it onto the hub's online catalog/inventory. Posnet is the
source of truth — so a pulled product upserts the matching hub product/variant
(keyed by SKU), refreshes its price, and sets its stock in the target warehouse.

Runs under the tenant's RLS scope (the catalog/inventory domain it calls is
RLS-scoped). Read-only against the POS source; the only writes are into the hub.
The real Posnet connector swaps in for the mock on the same
:class:`~libs.pos_source.PosSourceAdapter` contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.canonical_model import CanonicalProduct
from libs.pos_source import PosSourceAdapter

from ..domain.catalog import add_variant, create_product, find_variant_by_sku
from ..domain.inventory import apply_movement, get_inventory
from ..infrastructure.db.models import Warehouse


@dataclass(frozen=True, slots=True)
class PosSyncReport:
    """Outcome of one POS → hub catalog sync."""

    pulled: int
    created: int
    updated: int
    restocked: int


async def sync_catalog_from_pos(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    source: PosSourceAdapter,
    warehouse_id: UUID,
) -> PosSyncReport:
    """Pull ``source``'s catalog and project it onto the hub (Posnet = master)."""
    products: Sequence[CanonicalProduct] = await source.pull_catalog()
    created = updated = restocked = 0
    for cp in products:
        variant = await find_variant_by_sku(session, cp.sku)
        if variant is None:
            product = await create_product(
                session,
                tenant_id=tenant_id,
                name=cp.name,
                currency=cp.currency,
                category_path=list(cp.category_path),
            )
            variant = await add_variant(
                session,
                tenant_id=tenant_id,
                product_id=product.id,
                sku=cp.sku,
                base_price_minor=cp.price_minor,
                barcode=cp.barcode,
            )
            created += 1
        else:
            if variant.base_price_minor != cp.price_minor:
                variant.base_price_minor = cp.price_minor
                await session.flush()
            updated += 1

        if await _set_stock(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse_id,
            target=cp.stock_qty,
        ):
            restocked += 1

    return PosSyncReport(
        pulled=len(products), created=created, updated=updated, restocked=restocked
    )


async def sync_tenant_catalog_from_pos(
    session: AsyncSession, *, tenant_id: UUID, source: PosSourceAdapter
) -> PosSyncReport | None:
    """Sync one tenant's POS catalog into the hub — the ``make pos-sync`` cron unit.

    Mirrors POS stock into the tenant's primary online-sellable warehouse (lowest
    id) and returns the sync report, or ``None`` when the tenant has no
    online-sellable warehouse yet (nothing to mirror into). Single-warehouse
    mirror is the mock-first simplification: the POS reports one stock figure per
    product, so the hub holds it in one place; per-location mapping lands with the
    real Posnet interface (multi-store stock).

    Runs under the caller's tenant RLS scope, like :func:`sync_catalog_from_pos`.
    """
    warehouse_id = (
        await session.execute(
            select(Warehouse.id)
            .where(
                Warehouse.tenant_id == tenant_id,
                Warehouse.is_online_sellable.is_(True),
            )
            .order_by(Warehouse.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if warehouse_id is None:
        return None
    return await sync_catalog_from_pos(
        session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
    )


async def _set_stock(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    variant_id: UUID,
    warehouse_id: UUID,
    target: int,
) -> bool:
    """Drive the variant's stock in ``warehouse_id`` to ``target``. Returns
    whether a movement was applied (no-op when already at target)."""
    levels = await get_inventory(session, variant_id)
    current = next((lvl.qty for lvl in levels if lvl.warehouse_id == warehouse_id), None)
    if current is None:
        if target <= 0:
            return False
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            kind="in",
            qty=target,
            reference="posnet-sync",
        )
        return True
    delta = target - current
    if delta == 0:
        return False
    await apply_movement(
        session,
        tenant_id=tenant_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        kind="adjust",
        qty=delta,
        reference="posnet-sync",
    )
    return True
