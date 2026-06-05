"""AI-2.8 — the *full* crown-jewel loop, POS to POS (roadmap §17.6 + §17.7).

``test_e2e_mvp`` proves the channel half (hub → channel → order → reserve). This
extends it to the **complete hub loop**, with the same mock Posnet acting as both
ends — the source of truth on the way in and the sink on the way back:

1. **Pull (Posnet → hub):** ``sync_tenant_catalog_from_pos`` mirrors the Posnet
   catalog (product + price + stock) into the hub. (AI-2.8.1 / 2.8.4)
2. **Publish:** the merchant flips the product online (``set_online_published``).
3. **Push (hub → channel):** draining the outbox dispatches ``push_listing`` —
   the product appears on the marketplace with the Posnet price + stock. (AI-2.5)
4. **Order (channel → hub):** a channel order reserves hub stock (anti-oversell)
   and is **written back into Posnet** — the source of truth records the sale.
   (AI-2.5.5 + AI-2.8.3)
5. **Stock drops everywhere:** the reservation's movement re-pushes to the
   channel, so the marketplace stock falls too.
6. **Gate:** a second order beyond availability is rejected with **0 oversell**
   and is *not* written back to Posnet.

This is the demo G-V runs for a merchant: "your Posnet product is on the
marketplace in one step, the order lands back in Posnet, stock stays honest
everywhere." Outbound events drain from the real ``outbox_events`` table and
dispatch under tenant scope, exactly as the relay + consumer do in production.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import orjson
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import ChannelAdapter
from libs.canonical_model import CanonicalProduct
from libs.eventbus import Event
from mocks.mock_marketplace import MockStore
from mocks.mock_marketplace import create_app as create_mock_app
from mocks.mock_marketplace.models import OrderLineDTO
from mocks.mock_posnet import MockPosnetSource
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from services.core.app.domain.catalog import find_variant_by_sku, set_online_published
from services.core.app.domain.inventory import create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Inventory
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.dispatcher import DispatcherConfig, SyncDispatcher
from services.core.app.sync.order_ingest import ingest_channel_order
from services.core.app.sync.pos_ingest import sync_tenant_catalog_from_pos

SKU = "SKU-LOOP"
CHANNEL_CODE = "mock-marketplace"


# ----------------------------------------------------------------
# Seeding (scoped — the per-request POS path)
# ----------------------------------------------------------------


async def _seed_tenant(factory: async_sessionmaker[AsyncSession]) -> UUID:
    async with factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="T",
            country_code="AZ",
            plan="free",
            admin_email="loop@t.az",
            admin_subject="loop-subject",
        )
    return result.tenant_id


async def _seed_channel(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        return UUID(
            str(
                (
                    await session.execute(
                        text(
                            "INSERT INTO channels (tenant_id, code, name, status) "
                            "VALUES (:t, :c, 'Mock', 'active') RETURNING id"
                        ),
                        {"t": str(tenant_id), "c": CHANNEL_CODE},
                    )
                ).scalar_one()
            )
        )


async def _seed_warehouse(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        wh = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        return wh.id


async def _pull_from_pos(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, source: MockPosnetSource
) -> None:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        report = await sync_tenant_catalog_from_pos(session, tenant_id=tenant_id, source=source)
    assert report is not None and report.created == 1 and report.restocked == 1


async def _publish(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    """Publish the synced product online; return its variant id."""
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        variant = await find_variant_by_sku(session, SKU)
        assert variant is not None
        variant_id = variant.id
        await set_online_published(
            session, tenant_id=tenant_id, product_id=variant.product_id, published=True
        )
    return variant_id


# ----------------------------------------------------------------
# Read + drive helpers (mirroring the relay / consumer / webhook)
# ----------------------------------------------------------------


async def _inventory(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, variant_id: UUID
) -> tuple[int, int]:
    """Return ``(reserved, available)`` summed across the variant's levels."""
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        rows = (
            (await session.execute(select(Inventory).where(Inventory.variant_id == variant_id)))
            .scalars()
            .all()
        )
        reserved = sum(r.reserved_qty for r in rows)
        available = sum(r.qty - r.reserved_qty for r in rows)
    return reserved, available


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


async def _drain_outbox(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, dispatcher: SyncDispatcher
) -> None:
    """Read unpublished outbox rows (owner pool, like the relay), then dispatch
    each under tenant scope (like the consumer)."""
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
                text("UPDATE outbox_events SET published = true WHERE id = :id"),
                {"id": row[0]},
            )

    for row in rows:
        event = Event(event_id=row[0], event_type=row[2], tenant_id=row[1], payload=row[3] or {})
        async with factory() as session, session.begin():
            await apply_tenant_scope(session, tenant_id)
            await dispatcher(session, event)


async def _ingest(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    channel_id: UUID,
    adapter: MockMarketplaceAdapter,
    pos: MockPosnetSource,
    raw: bytes,
) -> str:
    """Mirror the webhook end to end: normalize → ingest (one tx) → **write a
    reserved order back into Posnet** (AI-2.8.3) → best-effort ack. Returns the
    persisted status."""
    order = adapter.normalize_webhook(body=raw, headers={})
    async with factory() as session, session.begin():
        outcome = await ingest_channel_order(
            session, tenant_id=tenant_id, channel_id=channel_id, order=order
        )
    if outcome.status == "reserved":
        await pos.push_order(order)
    if outcome.ack_status is not None:
        await adapter.acknowledge_order(
            channel_order_id=outcome.channel_order_id, status=outcome.ack_status
        )
    return outcome.status


def _order_body(store: MockStore, *, qty: int, customer: str) -> bytes:
    dto = store.seed_order(
        lines=[OrderLineDTO(sku=SKU, qty=qty, unit_price_minor=500, name="Loop item")],
        currency="AZN",
        customer_name=customer,
    )
    return orjson.dumps(dto.model_dump(mode="json"))


# ----------------------------------------------------------------
# The full loop
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_full_loop_posnet_to_channel_to_posnet(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    factory = async_session_factory
    store = MockStore()
    mock_app = create_mock_app(store)
    transport = httpx.ASGITransport(app=mock_app)  # type: ignore[arg-type]

    # The same Posnet is the source of truth on the way in and the sink on the
    # way back. Seed it with one product at price 500 / stock 10.
    posnet = MockPosnetSource()
    posnet.seed(
        CanonicalProduct(sku=SKU, name="Loop item", price_minor=500, currency="AZN", stock_qty=10)
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as client:
        adapter = MockMarketplaceAdapter(
            MockMarketplaceConfig(base_url="http://mock"), client=client
        )

        async def _factory(_channel: object) -> ChannelAdapter:
            return adapter

        dispatcher = SyncDispatcher(
            adapter_factory=_factory,
            config=DispatcherConfig(
                rate_per_second=1000, rate_burst=100, rate_acquire_timeout_seconds=5.0
            ),
        )

        tenant_id = await _seed_tenant(factory)
        channel_id = await _seed_channel(factory, tenant_id)
        await _seed_warehouse(factory, tenant_id)

        # --- Step 1: pull the Posnet catalog into the hub (Posnet = master) ---
        await _pull_from_pos(factory, tenant_id, posnet)
        # Pulled but not published → not on any channel yet.
        assert store.listing_by_sku(SKU) is None

        # --- Step 2: the merchant publishes the product online ---
        variant_id = await _publish(factory, tenant_id)

        # --- Step 3: drain → push_listing → visible on the channel (POS price+stock) ---
        await _drain_outbox(factory, tenant_id, dispatcher)
        listing = store.listing_by_sku(SKU)
        assert listing is not None, "published product should appear on the channel"
        assert listing.stock == 10
        assert listing.price_minor == 500

        # --- Step 4: channel order → reserve (anti-oversell) → Posnet write-back ---
        body = _order_body(store, qty=4, customer="Aysel")
        order_id = orjson.loads(body)["channel_order_id"]
        assert await _ingest(factory, tenant_id, channel_id, adapter, posnet, body) == "reserved"

        reserved, available = await _inventory(factory, tenant_id, variant_id)
        assert (reserved, available) == (4, 6)  # hub held 4 of 10
        # The sale was written back into Posnet — the source of truth has it.
        assert len(posnet.pushed_orders) == 1
        assert posnet.pushed_orders[0].channel_order_id == order_id
        assert posnet.pushed_orders[0].lines[0].sku == SKU
        assert store.last_ack(order_id) == "confirmed"

        # --- Step 5: stock drops everywhere → drain → channel reflects 6 ---
        await _drain_outbox(factory, tenant_id, dispatcher)
        dropped = store.listing_by_sku(SKU)
        assert dropped is not None and dropped.stock == 6

        # --- Gate: a second order beyond availability → rejected, 0 oversell ---
        body2 = _order_body(store, qty=9, customer="Babək")  # only 6 available
        order2_id = orjson.loads(body2)["channel_order_id"]
        assert await _ingest(factory, tenant_id, channel_id, adapter, posnet, body2) == "rejected"
        assert len(posnet.pushed_orders) == 1  # rejection NOT written back to Posnet
        assert store.last_ack(order2_id) == "cancelled"

        reserved_after, available_after = await _inventory(factory, tenant_id, variant_id)
        assert (reserved_after, available_after) == (4, 6)  # unchanged — never oversold
        assert await _channel_order_status(factory, channel_id, order2_id) == "rejected"
