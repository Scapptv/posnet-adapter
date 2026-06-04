"""AI-2.5.2 — SyncDispatcher end-to-end (real DB, fake adapter).

Proves the dispatcher loop: domain event → adapter call → ``channel_listings``
side effect. The adapter is a recording fake (the ``ChannelAdapter`` Protocol
is the only contract the dispatcher needs); real adapters land in AI-2.5.3.

Scenarios:

* ``catalog.variant.added`` on a published product → ``push_listing`` per
  active channel, ``channel_listings.external_listing_id`` populated.
* Variant on an unpublished product → no adapter calls (publish gate).
* ``inventory.movement.applied`` → ``push_stock`` per active listing with the
  aggregated available count.
* ``pricing.override.set`` → ``push_price`` per active listing with the
  resolved effective price.
* Retryable adapter error re-raised (consumer's backoff takes over).
* Permanent / auth errors swallowed with structured log (no retry storm).
* Circuit breaker opens after N consecutive failures, then skips dispatches.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import (
    AdapterAuthError,
    AdapterCapabilities,
    AdapterPermanentError,
    AdapterRetryableError,
    ChannelListingResult,
)
from libs.canonical_model import CanonicalOrder, CanonicalPrice, CanonicalProduct
from libs.eventbus import Event
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.events import (
    CATALOG_VARIANT_ADDED,
    INVENTORY_MOVEMENT_APPLIED,
    PRICING_OVERRIDE_SET,
)
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.domain.pricing import set_override
from services.core.app.infrastructure.db.models import Channel, ChannelListing
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.dispatcher import DispatcherConfig, SyncDispatcher

# ----------------------------------------------------------------
# Test-only adapter — records every call. Behaviour configurable per scenario.
# ----------------------------------------------------------------


@dataclass
class RecordingAdapter:
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        code="rec", name="Recorder", auth_kind="none"
    )

    raise_on: type[Exception] | None = None
    """If set, every push_* call raises this exception type."""

    pushes: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    listing_external_id: str = "EXT-1"
    listing_status: str = "active"

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        if self.raise_on is not None:
            raise self.raise_on("simulated")
        results = []
        for p in products:
            self.pushes.append(("listing", {"sku": p.sku, "stock_qty": p.stock_qty}))
            results.append(
                ChannelListingResult(
                    sku=p.sku,
                    external_listing_id=self.listing_external_id,
                    status=self.listing_status,
                )
            )
        return results

    async def push_stock(self, *, sku: str, qty: int) -> None:
        if self.raise_on is not None:
            raise self.raise_on("simulated")
        self.pushes.append(("stock", {"sku": sku, "qty": qty}))

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        if self.raise_on is not None:
            raise self.raise_on("simulated")
        self.pushes.append(("price", {"sku": sku, "price_minor": price.price_minor}))

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        return []

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        return None

    def map_category(self, canonical_category: Sequence[str]) -> str:
        return "/".join(canonical_category)


# ----------------------------------------------------------------
# Fixtures
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


@asynccontextmanager
async def _scoped(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        yield session


async def _seed_channel(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    *,
    code: str = "rec",
    status: str = "active",
) -> UUID:
    async with _scoped(factory, tenant_id) as session:
        channel = Channel(tenant_id=tenant_id, code=code, name=code.title(), status=status)
        session.add(channel)
        await session.flush()
        return channel.id


def _factory_for(adapter: RecordingAdapter):
    async def _factory(_channel: Channel) -> RecordingAdapter:
        return adapter

    return _factory


def _config(**overrides: object) -> DispatcherConfig:
    base: dict[str, object] = {
        "rate_per_second": 1000,  # fast for tests
        "rate_burst": 100,
        "rate_acquire_timeout_seconds": 5.0,
        "breaker_fail_max": 2,
        "breaker_reset_seconds": 60.0,
    }
    base.update(overrides)
    return DispatcherConfig(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------
# Variant added → push_listing
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_variant_added_pushes_listing_to_every_active_channel(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="d-l", email="d-l@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)

    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="SKU-1", base_price_minor=500
        )
        variant_id = variant.id

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=CATALOG_VARIANT_ADDED,
                tenant_id=tenant_id,
                payload={"variant_id": str(variant_id)},
            ),
        )

    assert [kind for kind, _ in adapter.pushes] == ["listing"]
    assert adapter.pushes[0][1]["sku"] == "SKU-1"

    async with _scoped(async_session_factory, tenant_id) as session:
        listing = (
            await session.execute(
                select(ChannelListing).where(
                    ChannelListing.variant_id == variant_id,
                    ChannelListing.channel_id == channel_id,
                )
            )
        ).scalar_one()
    assert listing.external_listing_id == "EXT-1"
    assert listing.status == "active"
    assert listing.last_synced_at is not None


@pytest.mark.integration
async def test_variant_on_unpublished_product_skips_push(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The online-publish gate (ADR-0018 §2) holds at the dispatcher boundary
    — no canonical, no push."""
    tenant_id = await _seed_tenant(async_session_factory, subject="d-up", email="d-up@t.az")
    await _seed_channel(async_session_factory, tenant_id)

    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        # online_published stays False by default
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S", base_price_minor=1
        )
        variant_id = variant.id

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=CATALOG_VARIANT_ADDED,
                tenant_id=tenant_id,
                payload={"variant_id": str(variant_id)},
            ),
        )

    assert adapter.pushes == []


# ----------------------------------------------------------------
# Movement applied → push_stock on existing active listings
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_movement_applied_pushes_stock_with_available_count(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="d-m", email="d-m@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="STK", base_price_minor=100
        )
        warehouse = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        # Pre-seed an active listing so push_stock has a target.
        session.add(
            ChannelListing(
                tenant_id=tenant_id,
                channel_id=channel_id,
                variant_id=variant.id,
                external_listing_id="EXT-PRE",
                status="active",
            )
        )
        await session.flush()
        variant_id, warehouse_id = variant.id, warehouse.id

    async with _scoped(async_session_factory, tenant_id) as session:
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            kind="in",
            qty=10,
        )
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            kind="reserve",
            qty=3,
        )

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=INVENTORY_MOVEMENT_APPLIED,
                tenant_id=tenant_id,
                payload={
                    "variant_id": str(variant_id),
                    "warehouse_id": str(warehouse_id),
                    "kind": "reserve",
                    "qty": 3,
                    "new_qty": 10,
                    "new_reserved_qty": 3,
                    "version": 2,
                },
            ),
        )

    assert [kind for kind, _ in adapter.pushes] == ["stock"]
    assert adapter.pushes[0][1] == {"sku": "STK", "qty": 7}  # 10 - 3 reserved


@pytest.mark.integration
async def test_movement_without_active_listing_skips_push(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Movement events for a variant the channel never listed → no push.
    Otherwise we'd hit the channel with a stock update for an unknown SKU."""
    tenant_id = await _seed_tenant(async_session_factory, subject="d-ml", email="d-ml@t.az")
    await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="X", base_price_minor=1
        )

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=INVENTORY_MOVEMENT_APPLIED,
                tenant_id=tenant_id,
                payload={
                    "variant_id": str(variant.id),
                    "warehouse_id": str(uuid4()),
                    "kind": "in",
                    "qty": 1,
                    "new_qty": 1,
                    "new_reserved_qty": 0,
                    "version": 1,
                },
            ),
        )

    assert adapter.pushes == []


# ----------------------------------------------------------------
# Override set → push_price
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_override_set_pushes_resolved_price(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="d-p", email="d-p@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="PRC", base_price_minor=1000
        )
        session.add(
            ChannelListing(
                tenant_id=tenant_id,
                channel_id=channel_id,
                variant_id=variant.id,
                external_listing_id="EXT-PRE",
                status="active",
            )
        )
        await session.flush()
        variant_id = variant.id
        await set_override(session, tenant_id=tenant_id, variant_id=variant_id, price_minor=750)

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=PRICING_OVERRIDE_SET,
                tenant_id=tenant_id,
                payload={
                    "variant_id": str(variant_id),
                    "override_id": str(uuid4()),
                    "store_id": None,
                    "price_minor": 750,
                    "valid_from": None,
                    "valid_to": None,
                },
            ),
        )

    assert [kind for kind, _ in adapter.pushes] == ["price"]
    assert adapter.pushes[0][1] == {"sku": "PRC", "price_minor": 750}


# ----------------------------------------------------------------
# Error classification
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_retryable_error_re_raises(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Retryable failures must propagate so the consumer's backoff fires —
    silently swallowing them would deadlock the change feed."""
    tenant_id = await _seed_tenant(async_session_factory, subject="d-r", email="d-r@t.az")
    await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter(raise_on=AdapterRetryableError)
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="R", base_price_minor=1
        )
        variant_id = variant.id

    with pytest.raises(AdapterRetryableError):
        async with _scoped(async_session_factory, tenant_id) as session:
            await dispatcher(
                session,
                Event(
                    event_type=CATALOG_VARIANT_ADDED,
                    tenant_id=tenant_id,
                    payload={"variant_id": str(variant_id)},
                ),
            )


@pytest.mark.integration
@pytest.mark.parametrize("exc_type", [AdapterAuthError, AdapterPermanentError])
async def test_non_retryable_errors_are_swallowed(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    exc_type: type[Exception],
) -> None:
    """Auth / Permanent errors don't deserve retries — the dispatcher logs
    them and returns. Reconciliation (5.6) cleans up the missed sync."""
    tenant_id = await _seed_tenant(
        async_session_factory, subject=f"d-{exc_type.__name__}", email="d-nr@t.az"
    )
    await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter(raise_on=exc_type)
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="N", base_price_minor=1
        )
        variant_id = variant.id

    # Does NOT raise — dispatcher logged and returned.
    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type=CATALOG_VARIANT_ADDED,
                tenant_id=tenant_id,
                payload={"variant_id": str(variant_id)},
            ),
        )


# ----------------------------------------------------------------
# Circuit breaker
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_breaker_opens_after_fail_max_then_skips(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """After ``breaker_fail_max`` consecutive retryable failures, the breaker
    opens — subsequent dispatches return without even calling the adapter,
    so an upstream outage doesn't snowball into a retry storm."""
    tenant_id = await _seed_tenant(async_session_factory, subject="d-cb", email="d-cb@t.az")
    await _seed_channel(async_session_factory, tenant_id)
    adapter = RecordingAdapter(raise_on=AdapterRetryableError)
    dispatcher = SyncDispatcher(
        adapter_factory=_factory_for(adapter),
        config=_config(breaker_fail_max=2),
    )

    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = True
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="CB", base_price_minor=1
        )
        variant_id = variant.id

    event = Event(
        event_type=CATALOG_VARIANT_ADDED,
        tenant_id=tenant_id,
        payload={"variant_id": str(variant_id)},
    )

    # Two real attempts trip the breaker — each re-raises.
    for _ in range(2):
        with pytest.raises(AdapterRetryableError):
            async with _scoped(async_session_factory, tenant_id) as session:
                await dispatcher(session, event)

    # Third attempt: breaker open. Adapter NOT called this time.
    calls_before = len(adapter.pushes)
    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(session, event)  # returns silently
    assert len(adapter.pushes) == calls_before  # adapter never invoked


# ----------------------------------------------------------------
# Unknown events
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_unknown_event_type_is_silently_skipped(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Foundation events (``identity.tenant.onboarded``) and any future event
    the dispatcher doesn't know about must skip without raising — otherwise
    the consumer would DLQ valid messages."""
    tenant_id = await _seed_tenant(async_session_factory, subject="d-uk", email="d-uk@t.az")
    adapter = RecordingAdapter()
    dispatcher = SyncDispatcher(adapter_factory=_factory_for(adapter), config=_config())

    async with _scoped(async_session_factory, tenant_id) as session:
        await dispatcher(
            session,
            Event(
                event_type="identity.tenant.onboarded",
                tenant_id=tenant_id,
                payload={"tenant_id": str(tenant_id)},
            ),
        )

    assert adapter.pushes == []
