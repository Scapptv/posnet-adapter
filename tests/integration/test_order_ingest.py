"""AI-2.5.5 — inbound order ingest + reservation (anti-oversell core).

Exercises ``ingest_channel_order`` / ``reserve_order`` directly against a real
DB (the webhook HTTP path is covered in ``test_webhook_ingress.py``; the full
POS↔channel loop in ``test_e2e_mvp.py``). The contract under test:

* a line reserves online-sellable stock → order ``reserved``, ``available`` drops;
* allocation spans multiple online warehouses, lowest id first;
* an unknown SKU or short stock → order ``rejected``, **no** stock moved;
* a redelivered order reserves exactly once (idempotency guard);
* non-online-sellable warehouses don't count toward reservation;
* a reservation emits ``inventory.movement.applied`` (so the dispatcher can
  push the drop back to every channel);
* a multi-line order is all-or-nothing;
* concurrent orders for the last units never oversell.

Ingest runs on a plain (owner) session with explicit ``tenant_id`` — exactly
how the webhook calls it on the system pool.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.canonical_model import CanonicalOrder, CanonicalOrderLine, CanonicalTotals
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import apply_movement
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Inventory, Warehouse
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.order_ingest import IngestOutcome, ingest_channel_order

# ----------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------


async def _seed_tenant(
    factory: async_sessionmaker[AsyncSession], *, subject: str, email: str
) -> UUID:
    async with factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="T",
            country_code="AZ",
            plan="free",
            admin_email=email,
            admin_subject=subject,
        )
    return result.tenant_id


async def _seed_channel(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        result = await session.execute(
            text(
                "INSERT INTO channels (tenant_id, code, name, status) "
                "VALUES (:t, 'mock', 'Mock', 'active') RETURNING id"
            ),
            {"t": str(tenant_id)},
        )
        return UUID(str(result.scalar_one()))


async def _seed_variant(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    *,
    sku: str,
    qty: int,
    online: bool = True,
) -> tuple[UUID, UUID]:
    """A product + variant + one warehouse stocked with ``qty``. Returns
    ``(variant_id, warehouse_id)``."""
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku=sku, base_price_minor=500
        )
        warehouse = Warehouse(
            tenant_id=tenant_id, name="W", type="store", is_online_sellable=online
        )
        session.add(warehouse)
        await session.flush()
        if qty:
            await apply_movement(
                session,
                tenant_id=tenant_id,
                variant_id=variant.id,
                warehouse_id=warehouse.id,
                kind="in",
                qty=qty,
            )
        return variant.id, warehouse.id


async def _add_warehouse(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    variant_id: UUID,
    *,
    qty: int,
    online: bool = True,
) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        warehouse = Warehouse(
            tenant_id=tenant_id, name="W2", type="store", is_online_sellable=online
        )
        session.add(warehouse)
        await session.flush()
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse.id,
            kind="in",
            qty=qty,
        )
        return warehouse.id


def _order(channel_order_id: str, *lines: tuple[str, int], currency: str = "AZN") -> CanonicalOrder:
    order_lines = tuple(
        CanonicalOrderLine(
            sku=sku, name=f"{sku} item", qty=qty, unit_price_minor=500, currency=currency
        )
        for sku, qty in lines
    )
    total = sum(line.unit_price_minor * line.qty for line in order_lines)
    return CanonicalOrder(
        channel_order_id=channel_order_id,
        lines=order_lines,
        totals=CanonicalTotals(subtotal_minor=total, grand_total_minor=total, currency=currency),
    )


async def _ingest(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    channel_id: UUID,
    order: CanonicalOrder,
) -> IngestOutcome:
    """Mirror the webhook: owner session, explicit tenant, one transaction."""
    async with factory() as session, session.begin():
        return await ingest_channel_order(
            session, tenant_id=tenant_id, channel_id=channel_id, order=order
        )


async def _levels(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, variant_id: UUID
) -> list[Inventory]:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        rows: Sequence[Inventory] = (
            (await session.execute(select(Inventory).where(Inventory.variant_id == variant_id)))
            .scalars()
            .all()
        )
        for row in rows:
            session.expunge(row)
        return list(rows)


async def _reserved_total(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, variant_id: UUID
) -> int:
    return sum(level.reserved_qty for level in await _levels(factory, tenant_id, variant_id))


async def _available_total(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, variant_id: UUID
) -> int:
    return sum(
        level.qty - level.reserved_qty for level in await _levels(factory, tenant_id, variant_id)
    )


async def _channel_order_status(
    factory: async_sessionmaker[AsyncSession], channel_id: UUID, channel_order_id: str
) -> str | None:
    async with factory() as session, session.begin():
        return (
            await session.execute(
                text(
                    "SELECT status FROM channel_orders "
                    "WHERE channel_id = :c AND channel_order_id = :o"
                ),
                {"c": str(channel_id), "o": channel_order_id},
            )
        ).scalar_one_or_none()


async def _channel_order_count(factory: async_sessionmaker[AsyncSession], channel_id: UUID) -> int:
    async with factory() as session, session.begin():
        return int(
            (
                await session.execute(
                    text("SELECT count(*) FROM channel_orders WHERE channel_id = :c"),
                    {"c": str(channel_id)},
                )
            ).scalar_one()
        )


async def _movement_kinds(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> list[str]:
    async with factory() as session, session.begin():
        rows = (
            await session.execute(
                text(
                    "SELECT payload->>'kind' FROM outbox_events "
                    "WHERE tenant_id = :t AND event_type = 'inventory.movement.applied'"
                ),
                {"t": str(tenant_id)},
            )
        ).all()
    return [r[0] for r in rows]


# ----------------------------------------------------------------
# Happy reservation
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_reserve_single_warehouse(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-1", email="oi1@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-A", qty=10)

    outcome = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-1", ("SKU-A", 3))
    )

    assert outcome.status == "reserved"
    assert outcome.ack_status == "confirmed"
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 3
    assert await _available_total(async_session_factory, tenant_id, variant_id) == 7
    assert await _channel_order_status(async_session_factory, channel_id, "ORD-1") == "reserved"


@pytest.mark.integration
async def test_reserve_spans_multiple_online_warehouses(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A line larger than any single warehouse draws from several, matching the
    aggregate online stock the channel was shown."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-2", email="oi2@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-B", qty=3)
    await _add_warehouse(async_session_factory, tenant_id, variant_id, qty=4)
    # A third warehouse the order never needs to reach: the allocation fills from
    # the first two and stops early (covers the remaining==0 break).
    await _add_warehouse(async_session_factory, tenant_id, variant_id, qty=5)

    outcome = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-2", ("SKU-B", 5))
    )

    assert outcome.status == "reserved"
    # 5 reserved across the online warehouses (3 + 4 + 5 = 12 available -> 7 left).
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 5
    assert await _available_total(async_session_factory, tenant_id, variant_id) == 7


# ----------------------------------------------------------------
# Rejection paths — never move stock
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_unknown_sku_rejects_without_moving_stock(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-3", email="oi3@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="REAL", qty=10)

    outcome = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-3", ("GHOST", 1))
    )

    assert outcome.status == "rejected"
    assert outcome.ack_status == "cancelled"
    assert outcome.reason is not None and "GHOST" in outcome.reason
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 0
    assert await _channel_order_status(async_session_factory, channel_id, "ORD-3") == "rejected"


@pytest.mark.integration
async def test_insufficient_stock_rejects(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-4", email="oi4@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-C", qty=5)

    outcome = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-4", ("SKU-C", 20))
    )

    assert outcome.status == "rejected"
    # Anti-oversell: nothing reserved when the order can't be fully covered.
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 0
    assert await _channel_order_status(async_session_factory, channel_id, "ORD-4") == "rejected"


@pytest.mark.integration
async def test_sold_out_warehouse_rejects_new_order(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Once a variant's online stock is fully reserved, its warehouse shows 0
    available — a new order finds nothing to take there and is rejected. (Sold
    out, not oversold.)"""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-sold", email="sold@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-SO", qty=3)

    first = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-SO1", ("SKU-SO", 3))
    )
    assert first.status == "reserved"

    second = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-SO2", ("SKU-SO", 1))
    )
    assert second.status == "rejected"
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 3  # unchanged


@pytest.mark.integration
async def test_non_online_warehouse_is_not_reservable(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Stock that sits only in a non-online-sellable warehouse must not back a
    channel order — the channel was never shown it."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-5", email="oi5@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(
        async_session_factory, tenant_id, sku="SKU-D", qty=10, online=False
    )

    outcome = await _ingest(
        async_session_factory, tenant_id, channel_id, _order("ORD-5", ("SKU-D", 1))
    )

    assert outcome.status == "rejected"
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 0


@pytest.mark.integration
async def test_multi_line_order_is_all_or_nothing(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """One short line rejects the whole order — the satisfiable line is rolled
    back, not partially shipped."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-6", email="oi6@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_a, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-OK", qty=10)
    variant_b, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-LOW", qty=1)

    outcome = await _ingest(
        async_session_factory,
        tenant_id,
        channel_id,
        _order("ORD-6", ("SKU-OK", 2), ("SKU-LOW", 5)),
    )

    assert outcome.status == "rejected"
    assert await _reserved_total(async_session_factory, tenant_id, variant_a) == 0
    assert await _reserved_total(async_session_factory, tenant_id, variant_b) == 0


# ----------------------------------------------------------------
# Idempotency + event emission
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_redelivered_order_reserves_once(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The UNIQUE(channel_id, channel_order_id) guard means a redelivered
    webhook can't reserve a second time."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-7", email="oi7@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-E", qty=10)
    order = _order("ORD-DUP", ("SKU-E", 4))

    first = await _ingest(async_session_factory, tenant_id, channel_id, order)
    second = await _ingest(async_session_factory, tenant_id, channel_id, order)

    assert first.status == "reserved"
    assert second.status == "duplicate"
    assert second.ack_status is None
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 4  # not 8
    assert await _channel_order_count(async_session_factory, channel_id) == 1


@pytest.mark.integration
async def test_reservation_emits_movement_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A reservation rides on ``apply_movement`` → it emits
    ``inventory.movement.applied`` (kind=reserve), which the dispatcher turns
    into ``push_stock`` on every channel (stock drops everywhere)."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-8", email="oi8@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_variant(async_session_factory, tenant_id, sku="SKU-F", qty=10)

    await _ingest(async_session_factory, tenant_id, channel_id, _order("ORD-8", ("SKU-F", 2)))

    assert "reserve" in await _movement_kinds(async_session_factory, tenant_id)


# ----------------------------------------------------------------
# Concurrency — the 0-oversell gate
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_concurrent_orders_for_last_units_never_oversell(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two orders race for two units, each wanting both. The SELECT FOR UPDATE
    lock in apply_movement serialises them — one reserves, the other is
    rejected, and the row never exceeds its stock."""
    tenant_id = await _seed_tenant(async_session_factory, subject="oi-9", email="oi9@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    variant_id, _ = await _seed_variant(async_session_factory, tenant_id, sku="SKU-G", qty=2)

    outcomes = await asyncio.gather(
        _ingest(async_session_factory, tenant_id, channel_id, _order("ORD-9A", ("SKU-G", 2))),
        _ingest(async_session_factory, tenant_id, channel_id, _order("ORD-9B", ("SKU-G", 2))),
    )

    statuses = sorted(o.status for o in outcomes)
    assert statuses == ["rejected", "reserved"]
    # 0 oversell: at most the two units were ever reserved.
    assert await _reserved_total(async_session_factory, tenant_id, variant_id) == 2
    assert await _channel_order_count(async_session_factory, channel_id) == 2
