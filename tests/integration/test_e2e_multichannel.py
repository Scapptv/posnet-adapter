"""Part V V1.2 — multi-channel fan-out: "stok hər yerdə düşür" at scale.

One product, TWO differently-shaped channels (mock-marketplace + mock-bazar).
Publishing fans the listing out to BOTH; an order on one channel reserves hub
stock and the drop is pushed to BOTH — proving the thesis holds across N
channels with no per-channel engine code (the dispatcher's fan-out over active
listings + two registered adapters do all of it). Real DB; both mocks over ASGI.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import ChannelAdapter
from libs.canonical_model import (
    CanonicalCustomer,
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalTotals,
    OrderStatus,
)
from libs.eventbus import Event
from mocks.mock_bazar import MockBazarStore
from mocks.mock_bazar import create_app as create_bz_app
from mocks.mock_marketplace import MockStore
from mocks.mock_marketplace import create_app as create_mm_app
from services.core.app.adapters.mock_bazar import MockBazarAdapter, MockBazarConfig
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from services.core.app.domain.catalog import add_variant, create_product, set_online_published
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.dispatcher import DispatcherConfig, SyncDispatcher
from services.core.app.sync.order_ingest import ingest_channel_order

SKU = "SKU-MC"
MM = "mock-marketplace"
BZ = "mock-bazar"


async def _seed_tenant(factory: async_sessionmaker[AsyncSession]) -> UUID:
    async with factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="T",
            country_code="AZ",
            plan="free",
            admin_email="mc@t.az",
            admin_subject="mc-sub",
        )
    return result.tenant_id


async def _seed_channel(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, code: str
) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        return UUID(
            str(
                (
                    await session.execute(
                        text(
                            "INSERT INTO channels (tenant_id, code, name, status) "
                            "VALUES (:t, :c, :c, 'active') RETURNING id"
                        ),
                        {"t": str(tenant_id), "c": code},
                    )
                ).scalar_one()
            )
        )


async def _seed_product(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, *, qty: int
) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku=SKU, base_price_minor=500
        )
        warehouse = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse.id,
            kind="in",
            qty=qty,
        )
        await set_online_published(
            session, tenant_id=tenant_id, product_id=product.id, published=True
        )
        return variant.id


async def _drain_outbox(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, dispatcher: SyncDispatcher
) -> None:
    async with factory() as session, session.begin():
        rows = (
            await session.execute(
                text(
                    "SELECT id, tenant_id, event_type, payload FROM outbox_events "
                    "WHERE published = false AND tenant_id = :t ORDER BY created_at, id"
                ),
                {"t": str(tenant_id)},
            )
        ).all()
        for row in rows:
            await session.execute(
                text("UPDATE outbox_events SET published = true WHERE id = :id"), {"id": row[0]}
            )
    for row in rows:
        event = Event(event_id=row[0], event_type=row[2], tenant_id=row[1], payload=row[3] or {})
        async with factory() as session, session.begin():
            await apply_tenant_scope(session, tenant_id)
            await dispatcher(session, event)


@pytest.mark.integration
async def test_publish_and_order_fan_out_to_both_channels(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    factory = async_session_factory
    mm_store, bz_store = MockStore(), MockBazarStore()
    mm_app, bz_app = create_mm_app(mm_store), create_bz_app(bz_store)

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mm_app),  # type: ignore[arg-type]
            base_url="http://mm",
        ) as mm_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=bz_app),  # type: ignore[arg-type]
            base_url="http://bz",
        ) as bz_client,
    ):
        mm_adapter = MockMarketplaceAdapter(
            MockMarketplaceConfig(base_url="http://mm"), client=mm_client
        )
        bz_adapter = MockBazarAdapter(MockBazarConfig(base_url="http://bz"), client=bz_client)
        adapters: dict[str, ChannelAdapter] = {MM: mm_adapter, BZ: bz_adapter}

        async def _factory(channel: object) -> ChannelAdapter:
            return adapters[channel.code]  # type: ignore[attr-defined]

        dispatcher = SyncDispatcher(
            adapter_factory=_factory,
            config=DispatcherConfig(
                rate_per_second=1000, rate_burst=100, rate_acquire_timeout_seconds=5.0
            ),
        )

        tenant_id = await _seed_tenant(factory)
        mm_channel_id = await _seed_channel(factory, tenant_id, MM)
        await _seed_channel(factory, tenant_id, BZ)
        await _seed_product(factory, tenant_id, qty=20)

        # --- Publish fans the listing out to BOTH channels ---
        await _drain_outbox(factory, tenant_id, dispatcher)
        mm_listing = mm_store.listing_by_sku(SKU)
        bz_product = bz_store.product_by_sku(SKU)
        assert mm_listing is not None and mm_listing.stock == 20
        assert bz_product is not None and bz_product.quantity == 20  # same product, 2nd channel

        # --- An order on ONE channel drops stock on BOTH ---
        order = CanonicalOrder(
            channel_order_id="MC-ORD-1",
            lines=(
                CanonicalOrderLine(sku=SKU, name="P", qty=4, unit_price_minor=500, currency="AZN"),
            ),
            totals=CanonicalTotals(subtotal_minor=2000, grand_total_minor=2000, currency="AZN"),
            status=OrderStatus.PENDING,
            customer=CanonicalCustomer(name="Aysel"),
        )
        async with factory() as session, session.begin():
            outcome = await ingest_channel_order(
                session, tenant_id=tenant_id, channel_id=mm_channel_id, order=order
            )
        assert outcome.status == "reserved"

        await _drain_outbox(factory, tenant_id, dispatcher)
        # 20 - 4 reserved = 16 available, pushed to BOTH channels — stok hər yerdə düşdü.
        assert mm_store.listing_by_sku(SKU).stock == 16  # type: ignore[union-attr]
        assert bz_store.product_by_sku(SKU).quantity == 16  # type: ignore[union-attr]
