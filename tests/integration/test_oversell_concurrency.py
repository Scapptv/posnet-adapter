"""AI-2.H3 — anti-oversell under real concurrency (audit A4/A5).

Coverage-theater problem: the previous suite proved ``_effect`` rejects an
oversell when called in isolation, but it never proved that two transactions
racing for the last unit can't both succeed. The ``SELECT ... FOR UPDATE`` lock
in ``apply_movement`` is what serialises them; if it were ever removed (or the
row-level lock were upgraded incorrectly), the unit tests would still pass but
production would oversell.

These tests launch concurrent ``apply_movement`` calls with their own
``AsyncSession`` + transaction, ``asyncio.gather`` them, and assert that the
final state matches what serial execution would have produced. The DB
``CHECK(reserved_qty <= qty)`` from migration 0010 is the belt-and-braces
backstop: even if the lock failed open, the constraint would refuse to commit
the over-reservation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.common import ConflictError
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Inventory
from services.core.app.infrastructure.db.tenant import apply_tenant_scope


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


async def _seed_stocked_variant(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    *,
    initial_qty: int,
    sku: str = "S",
) -> tuple[UUID, UUID]:
    """Return ``(variant_id, warehouse_id)`` for a tenant pre-stocked with
    ``initial_qty`` units (committed in its own transaction so the concurrent
    workers see the row when they begin)."""
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku=sku, base_price_minor=100
        )
        warehouse = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse.id,
            kind="in",
            qty=initial_qty,
        )
        return variant.id, warehouse.id


async def _reserve_one_unit(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    variant_id: UUID,
    warehouse_id: UUID,
    *,
    qty: int = 1,
) -> str:
    """One concurrent worker: open its own session+tx, scope to the tenant and
    try to reserve. Returns ``"ok"`` on success or ``"conflict"`` on anti-
    oversell. Other exceptions bubble up — the test wants to see them."""
    try:
        async with factory() as session, session.begin():
            await apply_tenant_scope(session, tenant_id)
            await apply_movement(
                session,
                tenant_id=tenant_id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                kind="reserve",
                qty=qty,
            )
        return "ok"
    except ConflictError:
        return "conflict"


async def _read_level(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    variant_id: UUID,
    warehouse_id: UUID,
) -> Inventory:
    from sqlalchemy import select

    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        result = await session.execute(
            select(Inventory).where(
                Inventory.variant_id == variant_id, Inventory.warehouse_id == warehouse_id
            )
        )
        inv = result.scalar_one()
        # Detach so attributes stay accessible after the session closes.
        session.expunge(inv)
        return inv


# ----------------------------------------------------------------------------
# Last-unit race — N reservations, M < N available — only M succeed.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_concurrent_reservations_for_last_unit_serialise(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The textbook anti-oversell case: ten clients race for three units. The
    ``SELECT FOR UPDATE`` lock serialises them, ``_effect`` rejects the seventh
    one onward (available 0 < 1), and the row ends at ``reserved == 3`` with
    seven losers seeing ``ConflictError``."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h3-last", email="last@t.az")
    variant_id, warehouse_id = await _seed_stocked_variant(
        async_session_factory, tenant_id, initial_qty=3
    )

    tasks: list[Awaitable[str]] = [
        _reserve_one_unit(async_session_factory, tenant_id, variant_id, warehouse_id)
        for _ in range(10)
    ]
    outcomes = await asyncio.gather(*tasks)

    assert outcomes.count("ok") == 3
    assert outcomes.count("conflict") == 7

    level = await _read_level(async_session_factory, tenant_id, variant_id, warehouse_id)
    assert level.qty == 3
    assert level.reserved_qty == 3
    assert level.qty - level.reserved_qty == 0


# ----------------------------------------------------------------------------
# Exact match — N reservations for N units — every one succeeds.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_concurrent_reservations_use_every_unit(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Five clients, five units — anti-oversell never refuses a legal request.
    The lock holds them in line, every one ends in ``ok``, and the row reads
    ``reserved == 5``."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h3-fit", email="fit@t.az")
    variant_id, warehouse_id = await _seed_stocked_variant(
        async_session_factory, tenant_id, initial_qty=5
    )

    tasks: list[Awaitable[str]] = [
        _reserve_one_unit(async_session_factory, tenant_id, variant_id, warehouse_id)
        for _ in range(5)
    ]
    outcomes = await asyncio.gather(*tasks)

    assert outcomes == ["ok"] * 5
    level = await _read_level(async_session_factory, tenant_id, variant_id, warehouse_id)
    assert level.reserved_qty == 5


# ----------------------------------------------------------------------------
# Sale path — concurrent "out" against limited stock — no oversell.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_concurrent_sells_never_oversell(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Channel sales path: concurrent ``out`` movements (cash-and-carry sale,
    not via a prior reservation) against two units of stock. Six tasks race;
    exactly two ship, four see a conflict, qty bottoms out at zero — never
    negative, which the CHECK would catch anyway."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h3-sell", email="sell@t.az")
    variant_id, warehouse_id = await _seed_stocked_variant(
        async_session_factory, tenant_id, initial_qty=2
    )

    async def _sell_one() -> str:
        try:
            async with async_session_factory() as session, session.begin():
                await apply_tenant_scope(session, tenant_id)
                await apply_movement(
                    session,
                    tenant_id=tenant_id,
                    variant_id=variant_id,
                    warehouse_id=warehouse_id,
                    kind="out",
                    qty=1,
                )
            return "ok"
        except ConflictError:
            return "conflict"

    outcomes = await asyncio.gather(*[_sell_one() for _ in range(6)])
    assert outcomes.count("ok") == 2
    assert outcomes.count("conflict") == 4

    level = await _read_level(async_session_factory, tenant_id, variant_id, warehouse_id)
    assert level.qty == 0
    assert level.reserved_qty == 0


# ----------------------------------------------------------------------------
# Optimistic-version path — concurrent writers with a stale ``expected_version``.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_stale_expected_version_loses_race(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """If a caller passes ``expected_version=N`` and the row has already moved
    on, the call must lose — even under concurrency the lock + version check
    delivers a deterministic loser."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h3-ver", email="ver@t.az")
    variant_id, warehouse_id = await _seed_stocked_variant(
        async_session_factory, tenant_id, initial_qty=5
    )
    # initial "in" bumped version 0 -> 1

    async def _move(qty: int, expected_version: int) -> str:
        try:
            async with async_session_factory() as session, session.begin():
                await apply_tenant_scope(session, tenant_id)
                await apply_movement(
                    session,
                    tenant_id=tenant_id,
                    variant_id=variant_id,
                    warehouse_id=warehouse_id,
                    kind="in",
                    qty=qty,
                    expected_version=expected_version,
                )
            return "ok"
        except ConflictError:
            return "stale"

    # Both pass expected_version=1. Whichever the lock lets in first updates the
    # row to version 2 and succeeds; the other sees version=2 != 1 and loses.
    outcomes = await asyncio.gather(
        _move(qty=1, expected_version=1), _move(qty=1, expected_version=1)
    )
    assert outcomes.count("ok") == 1
    assert outcomes.count("stale") == 1

    level = await _read_level(async_session_factory, tenant_id, variant_id, warehouse_id)
    assert level.qty == 6  # initial 5 + one winner's "in 1"
    assert level.version == 2
