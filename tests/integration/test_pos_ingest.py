"""AI-2.8 — POS → hub catalog sync (integration, RLS).

The inbound mirror of the dispatcher: a mock Posnet seeds canonical products,
``sync_catalog_from_pos`` projects them onto the hub (create/update product +
variant by SKU, refresh price, set stock). Posnet is the source of truth, so a
second run is a no-op and changed values overwrite the hub.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.canonical_model import CanonicalProduct
from mocks.mock_posnet import MockPosnetSource
from services.core.app.domain.catalog import add_variant, create_product, find_variant_by_sku
from services.core.app.domain.inventory import apply_movement, create_warehouse, get_inventory
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.pos_ingest import (
    sync_catalog_from_pos,
    sync_tenant_catalog_from_pos,
)


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


@asynccontextmanager
async def _scoped(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        yield session


async def _warehouse(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    async with _scoped(factory, tenant_id) as session:
        wh = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        return wh.id


def _product(sku: str, *, price: int, stock: int, name: str = "P") -> CanonicalProduct:
    return CanonicalProduct(sku=sku, name=name, price_minor=price, currency="AZN", stock_qty=stock)


async def _stock_of(session: AsyncSession, variant_id: UUID, warehouse_id: UUID) -> int:
    levels = await get_inventory(session, variant_id)
    return next((lvl.qty for lvl in levels if lvl.warehouse_id == warehouse_id), 0)


# ----------------------------------------------------------------
# Create
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_sync_creates_hub_products_from_pos(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-c", email="pos-c@t.az")
    warehouse_id = await _warehouse(async_session_factory, tenant_id)

    source = MockPosnetSource()
    source.seed(_product("PS-1", price=500, stock=10), _product("PS-2", price=250, stock=4))

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await sync_catalog_from_pos(
            session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
        )

    assert report.pulled == 2
    assert report.created == 2
    assert report.restocked == 2

    async with _scoped(async_session_factory, tenant_id) as session:
        v1 = await find_variant_by_sku(session, "PS-1")
        assert v1 is not None
        assert v1.base_price_minor == 500
        assert await _stock_of(session, v1.id, warehouse_id) == 10
        v2 = await find_variant_by_sku(session, "PS-2")
        assert v2 is not None
        assert await _stock_of(session, v2.id, warehouse_id) == 4


# ----------------------------------------------------------------
# Update existing (Posnet = master)
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_sync_updates_existing_price_and_stock(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-u", email="pos-u@t.az")
    warehouse_id = await _warehouse(async_session_factory, tenant_id)

    # Pre-seed the hub with a variant at price 500 / stock 3.
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="Old", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="UPD", base_price_minor=500
        )
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse_id,
            kind="in",
            qty=3,
        )
        variant_id = variant.id

    # Posnet now reports price 750 / stock 9.
    source = MockPosnetSource()
    source.seed(_product("UPD", price=750, stock=9))
    async with _scoped(async_session_factory, tenant_id) as session:
        report = await sync_catalog_from_pos(
            session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
        )

    assert report.created == 0
    assert report.updated == 1
    assert report.restocked == 1

    async with _scoped(async_session_factory, tenant_id) as session:
        v = await find_variant_by_sku(session, "UPD")
        assert v is not None and v.id == variant_id
        assert v.base_price_minor == 750
        assert await _stock_of(session, v.id, warehouse_id) == 9


# ----------------------------------------------------------------
# Idempotency
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_sync_is_idempotent(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-i", email="pos-i@t.az")
    warehouse_id = await _warehouse(async_session_factory, tenant_id)
    source = MockPosnetSource()
    source.seed(_product("IDEM", price=100, stock=5))

    async with _scoped(async_session_factory, tenant_id) as session:
        first = await sync_catalog_from_pos(
            session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
        )
    async with _scoped(async_session_factory, tenant_id) as session:
        second = await sync_catalog_from_pos(
            session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
        )

    assert first.created == 1 and first.restocked == 1
    # Nothing changed on the POS side → second run touches nothing.
    assert second.created == 0
    assert second.updated == 1  # matched the existing variant
    assert second.restocked == 0


# ----------------------------------------------------------------
# Tenant wrapper (the make pos-sync cron unit) — warehouse resolution
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_sync_tenant_mirrors_into_online_warehouse(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The cron wrapper resolves the tenant's online-sellable warehouse itself
    and mirrors POS stock into it."""
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-t", email="pos-t@t.az")
    warehouse_id = await _warehouse(async_session_factory, tenant_id)
    source = MockPosnetSource()
    source.seed(_product("TEN-1", price=300, stock=7))

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await sync_tenant_catalog_from_pos(session, tenant_id=tenant_id, source=source)

    assert report is not None
    assert report.pulled == 1 and report.created == 1 and report.restocked == 1
    async with _scoped(async_session_factory, tenant_id) as session:
        v = await find_variant_by_sku(session, "TEN-1")
        assert v is not None
        assert await _stock_of(session, v.id, warehouse_id) == 7


@pytest.mark.integration
async def test_sync_tenant_without_warehouse_returns_none(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A tenant with no online-sellable warehouse has nowhere to mirror stock —
    the wrapper returns None (the cron logs + skips) instead of failing."""
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-nw", email="pos-nw@t.az")
    source = MockPosnetSource()
    source.seed(_product("NW-1", price=100, stock=3))

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await sync_tenant_catalog_from_pos(session, tenant_id=tenant_id, source=source)

    assert report is None


@pytest.mark.integration
async def test_sync_zero_stock_product_creates_variant_without_movement(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A POS product reporting 0 stock is created in the hub but applies no
    inventory movement — there's nothing to mirror, so no first-create row."""
    tenant_id = await _seed_tenant(async_session_factory, subject="pos-z", email="pos-z@t.az")
    warehouse_id = await _warehouse(async_session_factory, tenant_id)
    source = MockPosnetSource()
    source.seed(_product("ZERO", price=200, stock=0))

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await sync_catalog_from_pos(
            session, tenant_id=tenant_id, source=source, warehouse_id=warehouse_id
        )

    assert report.created == 1
    assert report.restocked == 0  # 0 stock → no movement applied
    async with _scoped(async_session_factory, tenant_id) as session:
        v = await find_variant_by_sku(session, "ZERO")
        assert v is not None
        assert await _stock_of(session, v.id, warehouse_id) == 0
