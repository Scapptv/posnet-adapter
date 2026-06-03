"""Tenant-scoped inventory: stock levels + movement journal (AI-2.2).

``available = qty - reserved_qty``. Reservations are the anti-oversell mechanism:
a channel sale *reserves* before it ships, so the same unit cannot be promised
twice. Every level change goes through :func:`apply_movement`, which locks the row
(``SELECT ... FOR UPDATE``) so concurrent movements serialise, bumps ``version``
(optimistic-lock counter), and appends an immutable ``stock_movements`` row.

Like the catalog, foreign ids are re-checked under RLS so a cross-tenant id reads
as missing rather than being accepted by the FK alone (cf. AI-1.16 ``assign_role``).
``adjust`` carries a signed delta; the other kinds are positive quantities.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import ConflictError, NotFoundError, ValidationError

from ..infrastructure.db.models import Inventory, StockMovement, Variant, Warehouse

MOVEMENT_KINDS = frozenset({"in", "out", "reserve", "unreserve", "adjust"})


def _effect(kind: str, qty: int, on_hand: int, reserved: int) -> tuple[int, int]:
    """New ``(qty, reserved_qty)`` after applying ``kind``; raises if it would oversell."""
    available = on_hand - reserved
    if kind == "in":
        return on_hand + qty, reserved
    if kind == "out":
        if qty > available:
            raise ConflictError("insufficient available stock to remove")
        return on_hand - qty, reserved
    if kind == "reserve":
        if qty > available:
            raise ConflictError("insufficient available stock to reserve")
        return on_hand, reserved + qty
    if kind == "unreserve":
        if qty > reserved:
            raise ValidationError("cannot unreserve more than is reserved")
        return on_hand, reserved - qty
    # adjust — signed delta (stock-count correction / shrinkage)
    new_qty = on_hand + qty
    if new_qty < reserved:
        raise ValidationError("adjusted quantity would drop below reserved")
    return new_qty, reserved


async def create_warehouse(
    session: AsyncSession, *, tenant_id: UUID, name: str, type_: str
) -> Warehouse:
    warehouse = Warehouse(tenant_id=tenant_id, name=name, type=type_)
    session.add(warehouse)
    await session.flush()
    await session.refresh(warehouse)
    return warehouse


async def list_warehouses(session: AsyncSession) -> Sequence[Warehouse]:
    return (await session.execute(select(Warehouse).order_by(Warehouse.name))).scalars().all()


async def get_inventory(session: AsyncSession, variant_id: UUID) -> Sequence[Inventory]:
    """Stock levels for a variant across the tenant's warehouses (RLS-scoped)."""
    return (
        (await session.execute(select(Inventory).where(Inventory.variant_id == variant_id)))
        .scalars()
        .all()
    )


async def apply_movement(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    variant_id: UUID,
    warehouse_id: UUID,
    kind: str,
    qty: int,
    reference: str | None = None,
    expected_version: int | None = None,
) -> Inventory:
    """Apply one stock movement and return the updated level. Raises ``NotFoundError``
    (unknown variant/warehouse), ``ConflictError`` (oversell or stale ``expected_version``)
    or ``ValidationError`` (bad operation, e.g. removing from a non-existent level)."""
    if (await session.execute(select(Variant.id).where(Variant.id == variant_id))).first() is None:
        raise NotFoundError("variant not found in this tenant")
    if (
        await session.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id))
    ).first() is None:
        raise NotFoundError("warehouse not found in this tenant")

    inv = (
        await session.execute(
            select(Inventory)
            .where(Inventory.variant_id == variant_id, Inventory.warehouse_id == warehouse_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if inv is None:
        if kind not in ("in", "adjust"):
            raise ValidationError("no stock level for this variant/warehouse yet")
        inv = Inventory(
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            qty=0,
            reserved_qty=0,
            version=0,
        )
        session.add(inv)
        try:
            # First-create race: a concurrent movement may have already inserted
            # the row between our SELECT FOR UPDATE and this INSERT. The UNIQUE
            # (variant_id, warehouse_id) constraint catches it; the caller can
            # retry against the now-existing row (audit A3, AI-2.H2).
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "inventory level was concurrently created; retry the movement"
            ) from exc

    if expected_version is not None and expected_version != inv.version:
        raise ConflictError("inventory version is stale")

    inv.qty, inv.reserved_qty = _effect(kind, qty, inv.qty, inv.reserved_qty)
    inv.version += 1
    session.add(
        StockMovement(
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            kind=kind,
            qty=qty,
            reference=reference,
        )
    )
    await session.flush()
    await session.refresh(inv)
    return inv
