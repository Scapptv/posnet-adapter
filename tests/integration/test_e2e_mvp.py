"""AI-2.5.5 — the MVP end-to-end loop (roadmap §17.6, the AI-2.5 crown jewel).

Proves the whole product thesis in one test, against a real DB and the real
mock marketplace (wired over an in-process ASGI transport — no socket):

1. POS owns a product (canonical source of truth).
2. It's pushed to the channel as a listing (``push_listing``) → visible in the mock.
3. POS changes price + stock → synced to the channel (``push_price`` / ``push_stock``).
4. The channel takes an order → ingest reserves POS stock (anti-oversell) → the
   drop is pushed back so **stock falls everywhere**.
5. The order is acknowledged back to the channel.

Plus the gate's hard requirement: a follow-up order beyond availability is
**rejected with 0 oversell** — the reserved/available figures never exceed stock.

Outbound events are drained from the real ``outbox_events`` table (like the
relay) and dispatched under tenant scope (like the consumer); inbound runs the
same ``ingest_channel_order`` the webhook calls.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import orjson
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import ChannelAdapter
from libs.eventbus import Event
from mocks.mock_marketplace import MockStore
from mocks.mock_marketplace import create_app as create_mock_app
from mocks.mock_marketplace.models import OrderLineDTO
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import apply_movement
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.domain.pricing import set_override
from services.core.app.infrastructure.db.models import ChannelListing, Inventory, Warehouse
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.dispatcher import DispatcherConfig, SyncDispatcher
from services.core.app.sync.order_ingest import ingest_channel_order

SKU = "SKU-MVP"
CHANNEL_CODE = "mock-marketplace"


# ----------------------------------------------------------------
# Seeding helpers (scoped — the per-request POS path)
# ----------------------------------------------------------------


async def _seed_tenant(factory: async_sessionmaker[AsyncSession]) -> UUID:
    async with factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="T",
            country_code="AZ",
            plan="free",
            admin_email="e2e@t.az",
            admin_subject="e2e-subject",
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


async def _seed_variant(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, *, qty: int, base_price: int
) -> tuple[UUID, UUID]:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            sku=SKU,
            base_price_minor=base_price,
        )
        warehouse = Warehouse(tenant_id=tenant_id, name="W", type="store", is_online_sellable=True)
        session.add(warehouse)
        await session.flush()
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse.id,
            kind="in",
            qty=qty,
        )
        return variant.id, warehouse.id


async def _set_price(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, variant_id: UUID, price: int
) -> None:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        await set_override(session, tenant_id=tenant_id, variant_id=variant_id, price_minor=price)


async def _stock_in(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    variant_id: UUID,
    warehouse_id: UUID,
    qty: int,
) -> None:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            kind="in",
            qty=qty,
        )


# ----------------------------------------------------------------
# Read helpers
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


async def _listing_external_id(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    variant_id: UUID,
    channel_id: UUID,
) -> str | None:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        return (
            await session.execute(
                select(ChannelListing.external_listing_id).where(
                    ChannelListing.variant_id == variant_id,
                    ChannelListing.channel_id == channel_id,
                )
            )
        ).scalar_one_or_none()


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
    raw: bytes,
) -> str:
    """Mirror the webhook: normalize → ingest (one tx) → best-effort ack.
    Returns the persisted status."""
    order = adapter.normalize_webhook(body=raw, headers={})
    async with factory() as session, session.begin():
        outcome = await ingest_channel_order(
            session, tenant_id=tenant_id, channel_id=channel_id, order=order
        )
    if outcome.ack_status is not None:
        await adapter.acknowledge_order(
            channel_order_id=outcome.channel_order_id, status=outcome.ack_status
        )
    return outcome.status


def _order_body(store: MockStore, *, qty: int, customer: str) -> bytes:
    """Seed an order in the mock and render the webhook body the channel would
    POST (the same shape ``normalize_webhook`` parses)."""
    dto = store.seed_order(
        lines=[OrderLineDTO(sku=SKU, qty=qty, unit_price_minor=750, name="MVP item")],
        currency="AZN",
        customer_name=customer,
    )
    return orjson.dumps(dto.model_dump(mode="json"))


# ----------------------------------------------------------------
# The loop
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_mvp_pos_to_channel_round_trip(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    factory = async_session_factory
    store = MockStore()
    mock_app = create_mock_app(store)
    transport = httpx.ASGITransport(app=mock_app)  # type: ignore[arg-type]

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
        variant_id, warehouse_id = await _seed_variant(factory, tenant_id, qty=10, base_price=500)

        # --- Steps 1 + 2: POS product → push_listing → visible in the channel ---
        await _drain_outbox(factory, tenant_id, dispatcher)
        listing = store.listing_by_sku(SKU)
        assert listing is not None, "listing should be visible in the channel"
        assert listing.stock == 10
        assert listing.price_minor == 500
        assert await _listing_external_id(factory, tenant_id, variant_id, channel_id) is not None

        # --- Step 3: POS price + stock change → push_price / push_stock ---
        await _set_price(factory, tenant_id, variant_id, 750)
        await _drain_outbox(factory, tenant_id, dispatcher)
        priced = store.listing_by_sku(SKU)
        assert priced is not None and priced.price_minor == 750

        await _stock_in(factory, tenant_id, variant_id, warehouse_id, 5)  # 10 → 15
        await _drain_outbox(factory, tenant_id, dispatcher)
        restocked = store.listing_by_sku(SKU)
        assert restocked is not None and restocked.stock == 15

        # --- Step 4: channel order → ingest reserves → stock drops everywhere ---
        body = _order_body(store, qty=4, customer="Aysel")
        order_id = orjson.loads(body)["channel_order_id"]
        assert await _ingest(factory, tenant_id, channel_id, adapter, body) == "reserved"

        reserved, available = await _inventory(factory, tenant_id, variant_id)
        assert (reserved, available) == (4, 11)  # POS held 4
        assert await _channel_order_status(factory, channel_id, order_id) == "reserved"

        # --- Step 5: the order was acknowledged back to the channel ---
        assert store.last_ack(order_id) == "confirmed"

        # stock drops everywhere: the reservation's movement event pushes 11 out
        await _drain_outbox(factory, tenant_id, dispatcher)
        dropped = store.listing_by_sku(SKU)
        assert dropped is not None and dropped.stock == 11

        # --- Gate: a second order beyond availability is rejected, 0 oversell ---
        body2 = _order_body(store, qty=12, customer="Babək")  # only 11 available
        order2_id = orjson.loads(body2)["channel_order_id"]
        assert await _ingest(factory, tenant_id, channel_id, adapter, body2) == "rejected"
        assert store.last_ack(order2_id) == "cancelled"

        reserved_after, available_after = await _inventory(factory, tenant_id, variant_id)
        assert (reserved_after, available_after) == (4, 11)  # unchanged — never oversold
        assert await _channel_order_status(factory, channel_id, order2_id) == "rejected"

        await _drain_outbox(factory, tenant_id, dispatcher)  # rejection emitted no movement
        held = store.listing_by_sku(SKU)
        assert held is not None and held.stock == 11
