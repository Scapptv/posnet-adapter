"""Inbound channel order ingest (AI-2.5.5, roadmap §17.3 inbound / §17.6).

The outbound half of the hub (``dispatcher.py``) pushes catalog/stock/price to
channels. This module is the inbound half: a channel order — already normalized
into a :class:`~libs.canonical_model.CanonicalOrder` by the adapter and HMAC-
verified by the webhook endpoint — lands here, gets persisted exactly once, and
**reserves POS stock** so the same unit is never promised twice across channels.

Two functions, layered:

* :func:`reserve_order` — the anti-oversell core. For every order line it
  resolves SKU → variant (tenant-scoped), then greedily reserves the line
  quantity across the variant's *online-sellable* warehouses, lowest warehouse
  id first. Each reservation goes through :func:`~...domain.inventory.apply_movement`,
  so it inherits the ``SELECT ... FOR UPDATE`` lock + ``_effect`` guard + the
  ``inventory.movement.applied`` outbox event (which the dispatcher turns back
  into ``push_stock`` on *every* channel — that's how a marketplace sale makes
  stock drop everywhere). All-or-nothing: a single short line rolls the whole
  reservation back, so a partially-fulfillable order is rejected, not split.

* :func:`ingest_channel_order` — the orchestrator the webhook calls. It inserts
  the ``channel_orders`` row first (the ``UNIQUE(channel_id, channel_order_id)``
  constraint is the idempotency guard — a redelivered webhook short-circuits to
  ``duplicate`` *before* it can reserve a second time), then runs the
  reservation inside a SAVEPOINT so a rejection (unknown SKU / oversold) leaves
  the order persisted as ``rejected`` rather than losing the record.

Everything filters by ``tenant_id`` explicitly: the webhook runs on the system
(owner) pool, which is RLS-exempt, so the queries can't lean on
``app.current_tenant`` the way a per-request handler would.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.canonical_model import CanonicalOrder
from libs.common import ConflictError, NotFoundError, ValidationError

from ..domain.inventory import apply_movement
from ..infrastructure.db.models import ChannelOrder, Inventory, Variant, Warehouse

# channel_orders.status → the status we acknowledge back to the channel, in the
# channel's own vocabulary (mock/Trendyol style: pending|confirmed|fulfilled|
# cancelled). A real adapter with a different vocabulary maps it in
# ``acknowledge_order``; the hub speaks its canonical status here.
_ACK_STATUS: dict[str, str] = {"reserved": "confirmed", "rejected": "cancelled"}


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """The result of ingesting one webhook delivery.

    ``status`` is the persisted ``channel_orders.status`` (``reserved`` /
    ``rejected``) or ``duplicate`` for a redelivery. ``ack_status`` is what the
    caller should acknowledge back to the channel — ``None`` for a duplicate
    (the first delivery already acknowledged it).
    """

    channel_order_id: str
    status: str
    ack_status: str | None
    reason: str | None = None


async def reserve_order(session: AsyncSession, *, tenant_id: UUID, order: CanonicalOrder) -> None:
    """Reserve every line of ``order`` against online-sellable stock.

    Raises :class:`~libs.common.NotFoundError` if a line's SKU isn't a variant
    in ``tenant_id``, or :class:`~libs.common.ConflictError` if the online
    stock can't cover a line (anti-oversell). The caller runs this inside a
    SAVEPOINT, so any raise rolls back *all* of the order's reservations —
    reservation is all-or-nothing.
    """
    online_warehouse_ids = (
        (
            await session.execute(
                select(Warehouse.id).where(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.is_online_sellable.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    for line in order.lines:
        variant_id = (
            await session.execute(
                select(Variant.id).where(Variant.tenant_id == tenant_id, Variant.sku == line.sku)
            )
        ).scalar_one_or_none()
        if variant_id is None:
            raise NotFoundError(f"sku {line.sku!r} is not a variant in this tenant")

        remaining = line.qty
        if online_warehouse_ids:
            # Plan the allocation from a *column* read, not entities: loading the
            # Inventory rows into the identity map here would make
            # ``apply_movement``'s ``SELECT ... FOR UPDATE`` hand back the cached
            # (pre-lock) object instead of the freshly-locked values — and the
            # anti-oversell guard would then judge against stale stock. Reading
            # bare columns keeps the row unmapped so the locked read is the first.
            planned = (
                await session.execute(
                    select(Inventory.warehouse_id, Inventory.qty, Inventory.reserved_qty)
                    .where(
                        Inventory.tenant_id == tenant_id,
                        Inventory.variant_id == variant_id,
                        Inventory.warehouse_id.in_(online_warehouse_ids),
                    )
                    .order_by(Inventory.warehouse_id)
                )
            ).all()
            for warehouse_id, qty, reserved_qty in planned:
                if remaining == 0:
                    break
                take = min(qty - reserved_qty, remaining)
                if take <= 0:
                    continue
                await apply_movement(
                    session,
                    tenant_id=tenant_id,
                    variant_id=variant_id,
                    warehouse_id=warehouse_id,
                    kind="reserve",
                    qty=take,
                    reference=f"channel-order:{order.channel_order_id}",
                )
                remaining -= take

        if remaining > 0:
            raise ConflictError(
                f"insufficient online stock to reserve {line.qty} of sku {line.sku!r}"
            )


async def ingest_channel_order(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    order: CanonicalOrder,
) -> IngestOutcome:
    """Persist + reserve one inbound channel order (idempotent).

    Runs inside the caller's transaction. Inserts the ``channel_orders`` row
    first so a redelivery trips the UNIQUE constraint before reserving twice,
    then reserves in a SAVEPOINT so a rejection still leaves the order on
    record.
    """
    order_row = ChannelOrder(
        tenant_id=tenant_id,
        channel_id=channel_id,
        channel_order_id=order.channel_order_id,
        canonical_payload=order.model_dump(mode="json"),
        status="received",
    )
    try:
        async with session.begin_nested():
            session.add(order_row)
    except IntegrityError:
        # Redelivered webhook — already ingested. The first delivery reserved
        # (or rejected) and acknowledged it; do neither again.
        return IngestOutcome(
            channel_order_id=order.channel_order_id, status="duplicate", ack_status=None
        )

    try:
        async with session.begin_nested():
            await reserve_order(session, tenant_id=tenant_id, order=order)
    except (ConflictError, NotFoundError, ValidationError) as exc:
        order_row.status = "rejected"
        return IngestOutcome(
            channel_order_id=order.channel_order_id,
            status="rejected",
            ack_status=_ACK_STATUS["rejected"],
            reason=str(exc),
        )

    order_row.status = "reserved"
    return IngestOutcome(
        channel_order_id=order.channel_order_id,
        status="reserved",
        ack_status=_ACK_STATUS["reserved"],
    )
