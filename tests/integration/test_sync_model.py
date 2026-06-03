"""AI-2.H5 — sync model enabler (audit B2/B3/B4/B6, ADR-0018).

The pieces the adapter framework (AI-2.5) lands on:

* ``Warehouse.is_online_sellable`` — which warehouses contribute to the online
  ``available`` figure. Default true so existing warehouses stay sellable.
* ``Product.online_published`` — explicit opt-in gate. Default false so a
  product is never pushed to channels until the operator releases it.
* ``channels`` + ``channel_listings`` — variant ↔ external listing per channel.
* ``build_canonical_product`` — the orchestrator that folds Product, Variant,
  Inventory[] and resolved Price into a ``CanonicalProduct``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import (
    Channel,
    ChannelListing,
    Product,
    Warehouse,
)
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.canonical import build_canonical_product


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


# ----------------------------------------------------------------------------
# B2 / B3 — schema defaults (online-sellable true, online-published false).
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_warehouse_default_is_online_sellable_true(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Existing warehouses keep selling online — the safe migration default."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-w", email="w@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        wh = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
    assert wh.is_online_sellable is True


@pytest.mark.integration
async def test_product_default_online_published_false(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A freshly created product is NOT online-published. The operator must
    flip the flag — no inadvertent push to channels."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-p", email="p@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
    assert product.online_published is False


# ----------------------------------------------------------------------------
# B4 — channel schema: uniqueness + tenant isolation.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_channel_code_unique_per_tenant(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two channels with the same code can't coexist in one tenant."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-c", email="c@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        session.add(Channel(tenant_id=tenant_id, code="trendyol", name="Trendyol"))
        await session.flush()

    with pytest.raises(IntegrityError):
        async with _scoped(async_session_factory, tenant_id) as session:
            session.add(Channel(tenant_id=tenant_id, code="trendyol", name="Trendyol Again"))
            await session.flush()


@pytest.mark.integration
async def test_channel_listing_one_per_variant_per_channel(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A variant has at most one listing per channel — no double-mapping."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-cl", email="cl@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S1", base_price_minor=100
        )
        channel = Channel(tenant_id=tenant_id, code="trendyol", name="Trendyol")
        session.add(channel)
        await session.flush()
        channel_id, variant_id = channel.id, variant.id

        session.add(
            ChannelListing(
                tenant_id=tenant_id,
                channel_id=channel_id,
                variant_id=variant_id,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        async with _scoped(async_session_factory, tenant_id) as session:
            session.add(
                ChannelListing(
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    variant_id=variant_id,
                )
            )
            await session.flush()


@pytest.mark.integration
async def test_channel_listing_external_listing_id_unique_per_channel(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two distinct variants can't share the same external listing id on one
    channel — the partial UNIQUE catches the conflict."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-ex", email="ex@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        v1 = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="A", base_price_minor=1
        )
        v2 = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="B", base_price_minor=1
        )
        channel = Channel(tenant_id=tenant_id, code="trendyol", name="Trendyol")
        session.add(channel)
        await session.flush()
        channel_id, v1_id, v2_id = channel.id, v1.id, v2.id

        session.add(
            ChannelListing(
                tenant_id=tenant_id,
                channel_id=channel_id,
                variant_id=v1_id,
                external_listing_id="TR-12345",
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        async with _scoped(async_session_factory, tenant_id) as session:
            session.add(
                ChannelListing(
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    variant_id=v2_id,
                    external_listing_id="TR-12345",  # collides
                )
            )
            await session.flush()


@pytest.mark.integration
async def test_channel_listing_null_external_ids_coexist(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two listings with no external id yet (pending-push state) must coexist —
    the UNIQUE is partial on non-NULL."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-nn", email="nn@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        v1 = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="A", base_price_minor=1
        )
        v2 = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="B", base_price_minor=1
        )
        channel = Channel(tenant_id=tenant_id, code="trendyol", name="Trendyol")
        session.add(channel)
        await session.flush()
        session.add(ChannelListing(tenant_id=tenant_id, channel_id=channel.id, variant_id=v1.id))
        session.add(ChannelListing(tenant_id=tenant_id, channel_id=channel.id, variant_id=v2.id))
        await session.flush()  # both NULL external_listing_id — should not collide


@pytest.mark.integration
async def test_channels_are_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """RLS: tenant B never sees tenant A's channels."""
    t1 = await _seed_tenant(async_session_factory, subject="h5-t1", email="t1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="h5-t2", email="t2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        session.add(Channel(tenant_id=t1, code="trendyol", name="T1 Trendyol"))
        await session.flush()
    async with _scoped(async_session_factory, t2) as session:
        rows = (await session.execute(select(Channel))).scalars().all()
    assert rows == []


# ----------------------------------------------------------------------------
# B6 — build_canonical_product orchestrator.
# ----------------------------------------------------------------------------


_AT = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


@pytest.mark.integration
async def test_build_canonical_product_unpublished_returns_none(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Default product (online_published=false) → orchestrator returns None,
    so the sync engine never pushes it."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-up", email="up@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S", base_price_minor=100
        )
        result = await build_canonical_product(session, variant_id=variant.id, at=_AT)
    assert result is None


@pytest.mark.integration
async def test_build_canonical_product_aggregates_only_online_warehouses(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two warehouses, one B2B (non-sellable). The canonical ``stock_qty``
    reflects only the online-sellable warehouse."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-ag", email="ag@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(
            session, tenant_id=tenant_id, name="Coca Cola", currency="AZN"
        )
        product.online_published = True
        variant = await add_variant(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            sku="CC-500",
            barcode="8690000000001",
            base_price_minor=300,
            name="500ml",
        )
        online_wh = await create_warehouse(session, tenant_id=tenant_id, name="Main", type_="store")
        b2b_wh = await create_warehouse(session, tenant_id=tenant_id, name="B2B", type_="store")
        b2b_wh.is_online_sellable = False
        await session.flush()
        # Stock both warehouses.
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=online_wh.id,
            kind="in",
            qty=10,
        )
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=online_wh.id,
            kind="reserve",
            qty=2,
        )
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=b2b_wh.id,
            kind="in",
            qty=500,
        )
        result = await build_canonical_product(session, variant_id=variant.id, at=_AT)

    assert result is not None
    assert result.sku == "CC-500"
    assert result.barcode == "8690000000001"
    assert result.name == "500ml"  # variant name wins
    assert result.stock_qty == 8  # 10 - 2 reserved (B2B's 500 excluded)
    assert result.price_minor == 300
    assert result.currency == "AZN"


@pytest.mark.integration
async def test_build_canonical_product_uses_resolved_price_with_override(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """An active price override is reflected in the canonical snapshot."""
    from services.core.app.domain.pricing import set_override

    tenant_id = await _seed_tenant(async_session_factory, subject="h5-pr", email="pr@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            sku="S",
            base_price_minor=1000,
        )
        await set_override(session, tenant_id=tenant_id, variant_id=variant.id, price_minor=750)
        result = await build_canonical_product(session, variant_id=variant.id, at=_AT)

    assert result is not None
    assert result.price_minor == 750  # override beats base


@pytest.mark.integration
async def test_build_canonical_product_unknown_variant_returns_none(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from uuid import uuid4

    tenant_id = await _seed_tenant(async_session_factory, subject="h5-uv", email="uv@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        result = await build_canonical_product(session, variant_id=uuid4(), at=_AT)
    assert result is None


@pytest.mark.integration
async def test_build_canonical_product_zero_stock_when_no_inventory(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A published product with no inventory rows surfaces with stock_qty 0 —
    a valid out-of-stock snapshot, not a None."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-zs", email="zs@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S", base_price_minor=100
        )
        result = await build_canonical_product(session, variant_id=variant.id, at=_AT)
    assert result is not None
    assert result.stock_qty == 0


# ----------------------------------------------------------------------------
# Migration sanity — new tables exist and have grants + RLS.
# ----------------------------------------------------------------------------


@pytest.mark.integration
def test_channels_and_listings_tables_exist_with_rls(migrated_db: None, pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('channels', 'channel_listings') AND relkind = 'r'"
        )
        rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    assert "channels" in rows and rows["channels"] == (True, True)
    assert "channel_listings" in rows and rows["channel_listings"] == (True, True)


@pytest.mark.integration
def test_app_role_has_full_dml_on_channel_tables(migrated_db: None, pg_dsn: str) -> None:
    """``channels`` and ``channel_listings`` are not journals — full DML."""
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'posnet_app' AND table_name IN ('channels', 'channel_listings')"
        )
        grants: dict[str, set[str]] = {}
        for table, priv in cur.fetchall():
            grants.setdefault(table, set()).add(priv)
    for table in ("channels", "channel_listings"):
        assert grants[table] >= {"SELECT", "INSERT", "UPDATE", "DELETE"}


@pytest.mark.integration
async def test_existing_warehouse_is_online_sellable_set_by_default(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The migration default (``true``) means every row reads ``true`` even
    without us setting it explicitly — verifies the server_default works."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-sd", email="sd@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        await session.execute(
            text("INSERT INTO warehouses (tenant_id, name, type) VALUES (:t, 'X', 'store')"),
            {"t": tenant_id},
        )
        warehouses = (await session.execute(select(Warehouse))).scalars().all()
    assert all(w.is_online_sellable is True for w in warehouses)


@pytest.mark.integration
async def test_existing_product_online_published_default_false(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A raw insert (no explicit flag) reads ``false`` — confirms the
    safer-default migration."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h5-pd", email="pd@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        await session.execute(
            text("INSERT INTO products (tenant_id, name, currency) VALUES (:t, 'X', 'AZN')"),
            {"t": tenant_id},
        )
        products = (await session.execute(select(Product))).scalars().all()
    assert all(p.online_published is False for p in products)
