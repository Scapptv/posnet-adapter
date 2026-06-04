"""AI-2.5.6.2 — channel reconciliation: drift detect + repair (roadmap §17.4).

The gate criterion: reconciliation finds *injected* drift and repairs it. The
headline tests use the real :class:`MockMarketplaceAdapter` + mock store — a
listing is pushed, drift is injected channel-side, reconcile runs, and the
mock store reads back repaired to POS truth. Edge branches (unpublished, not
listed, fetch error, repair failure) use a configurable stub adapter for
precise control.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import (
    AdapterCapabilities,
    AdapterNotFoundError,
    AdapterRetryableError,
    ChannelListingResult,
    ChannelListingSnapshot,
)
from libs.canonical_model import CanonicalOrder, CanonicalPrice, CanonicalProduct
from mocks.mock_marketplace import create_app as create_mock_app
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Channel, ChannelListing
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.canonical import build_canonical_product
from services.core.app.sync.guard import ChannelGuard, GuardConfig
from services.core.app.sync.reconcile import reconcile_channel, reconcile_tenant

# ----------------------------------------------------------------
# Fast guard (no real throttling in tests)
# ----------------------------------------------------------------


def _fast_guard() -> ChannelGuard:
    return ChannelGuard(
        GuardConfig(rate_per_second=1000, rate_burst=100, rate_acquire_timeout_seconds=5.0)
    )


# ----------------------------------------------------------------
# Configurable stub adapter for edge branches
# ----------------------------------------------------------------


@dataclass
class _StubAdapter:
    """Reconcile only calls fetch_listing + push_stock/push_price; this stub
    makes each one's behaviour configurable so the branch tests are exact."""

    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        code="stub", name="Stub", auth_kind="none", supports_fetch_listing=True
    )
    snapshot: ChannelListingSnapshot | None = None
    fetch_error: type[Exception] | None = None
    push_error: type[Exception] | None = None
    pushes: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def fetch_listing(self, *, sku: str) -> ChannelListingSnapshot | None:
        if self.fetch_error is not None:
            raise self.fetch_error("simulated fetch failure")
        return self.snapshot

    async def push_stock(self, *, sku: str, qty: int) -> None:
        if self.push_error is not None:
            raise self.push_error("simulated push failure")
        self.pushes.append(("stock", {"sku": sku, "qty": qty}))

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        if self.push_error is not None:
            raise self.push_error("simulated push failure")
        self.pushes.append(("price", {"sku": sku, "price_minor": price.price_minor}))

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        return []

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        return []

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        return None

    def map_category(self, canonical_category: Sequence[str]) -> str:
        return "/".join(canonical_category)

    def normalize_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> CanonicalOrder:
        raise NotImplementedError


# ----------------------------------------------------------------
# Mock-backed real adapter
# ----------------------------------------------------------------


def _client_for_app(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://mock-marketplace")


@pytest.fixture
async def mock_adapter() -> AsyncIterator[tuple[MockMarketplaceAdapter, Any]]:
    mock = create_mock_app()
    client = _client_for_app(mock)
    adapter = MockMarketplaceAdapter(
        MockMarketplaceConfig(base_url="http://mock-marketplace"), client=client
    )
    try:
        yield adapter, mock.state.store
    finally:
        await adapter.aclose()


# ----------------------------------------------------------------
# Seed helpers
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


async def _seed_channel(factory: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    async with _scoped(factory, tenant_id) as session:
        channel = Channel(
            tenant_id=tenant_id, code="mock-marketplace", name="Mock", status="active"
        )
        session.add(channel)
        await session.flush()
        return channel.id


async def _seed_listed_variant(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    channel_id: UUID,
    *,
    sku: str,
    qty: int,
    base_price: int = 500,
    published: bool = True,
    adapter: MockMarketplaceAdapter | None = None,
) -> UUID:
    """Seed a (published) variant with ``qty`` stock and an active
    ``channel_listings`` row. If ``adapter`` is given, push the listing to the
    channel first (so the mock store has it); otherwise just create the DB row
    with a placeholder external id."""
    async with _scoped(factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        product.online_published = published
        variant = await add_variant(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            sku=sku,
            base_price_minor=base_price,
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
        variant_id = variant.id

    external_id = f"EXT-{sku}"
    if adapter is not None:
        async with _scoped(factory, tenant_id) as session:
            canonical = await build_canonical_product(
                session, variant_id=variant_id, at=datetime.now(UTC)
            )
        assert canonical is not None
        external_id = (await adapter.push_listing([canonical]))[0].external_listing_id

    async with _scoped(factory, tenant_id) as session:
        session.add(
            ChannelListing(
                tenant_id=tenant_id,
                channel_id=channel_id,
                variant_id=variant_id,
                external_listing_id=external_id,
                status="active",
            )
        )
    return variant_id


async def _channel(factory: async_sessionmaker[AsyncSession], tenant_id: UUID, channel_id: UUID):  # type: ignore[no-untyped-def]
    async with _scoped(factory, tenant_id) as session:
        return (await session.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()


# ================================================================
# GATE — injected drift found + repaired (real mock adapter)
# ================================================================


@pytest.mark.integration
async def test_reconcile_repairs_injected_stock_drift(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    """Push a listing (channel stock 10), inject channel-side drift (3), then
    reconcile — it detects 3 != 10 and repairs the channel back to 10."""
    adapter, store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-s", email="rec-s@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(
        async_session_factory, tenant_id, channel_id, sku="DRIFT-1", qty=10, adapter=adapter
    )

    assert store.listing_by_sku("DRIFT-1").stock == 10
    store.set_stock(seller_sku="DRIFT-1", qty=3)  # inject drift

    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    assert len(results) == 1
    r = results[0]
    assert r.sku == "DRIFT-1"
    assert r.pos_stock == 10
    assert r.channel_stock == 3
    assert r.stock_drift is True
    assert r.price_drift is False
    assert r.repaired is True
    # The repair landed on the channel.
    assert store.listing_by_sku("DRIFT-1").stock == 10


@pytest.mark.integration
async def test_reconcile_repairs_injected_price_drift(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    adapter, store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-p", email="rec-p@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(
        async_session_factory,
        tenant_id,
        channel_id,
        sku="PRC-1",
        qty=5,
        base_price=500,
        adapter=adapter,
    )

    assert store.listing_by_sku("PRC-1").price_minor == 500
    store.set_price(seller_sku="PRC-1", price_minor=999, currency="AZN")  # inject drift

    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    r = results[0]
    assert r.price_drift is True
    assert r.stock_drift is False
    assert r.repaired is True
    assert store.listing_by_sku("PRC-1").price_minor == 500


@pytest.mark.integration
async def test_reconcile_no_drift_is_noop(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    """Channel already agrees with POS — no drift, no repair push."""
    adapter, store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-n", email="rec-n@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(
        async_session_factory, tenant_id, channel_id, sku="OK-1", qty=7, adapter=adapter
    )

    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    r = results[0]
    assert r.stock_drift is False
    assert r.price_drift is False
    assert r.repaired is False
    assert r.channel_stock == 7
    assert store.listing_by_sku("OK-1").stock == 7  # untouched — no repair push


# ================================================================
# Skip branches
# ================================================================


@pytest.mark.integration
async def test_reconcile_skips_unpublished(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    """A listing whose product is no longer online-published is skipped before
    any channel call (build_canonical_product returns None)."""
    adapter, _store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-u", email="rec-u@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(
        async_session_factory, tenant_id, channel_id, sku="UNPUB", qty=5, published=False
    )

    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    assert results[0].note == "not online-published"
    assert results[0].repaired is False


@pytest.mark.integration
async def test_reconcile_skips_not_listed_on_channel(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    """POS thinks it's listed (external id set) but the channel returns 404 →
    skip with a clear note (no repair)."""
    adapter, _store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-nl", email="rec-nl@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    # adapter=None → no push, so the mock store has nothing for this sku.
    await _seed_listed_variant(async_session_factory, tenant_id, channel_id, sku="GHOST", qty=5)

    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    assert results[0].note == "not listed on channel"
    assert results[0].channel_stock is None


@pytest.mark.integration
async def test_reconcile_skips_fetch_error_and_continues(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A fetch that raises is logged + skipped; the run does not abort — two
    listings both surface a skip result rather than crashing the batch."""
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-fe", email="rec-fe@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(async_session_factory, tenant_id, channel_id, sku="FE-1", qty=5)
    await _seed_listed_variant(async_session_factory, tenant_id, channel_id, sku="FE-2", qty=5)

    adapter = _StubAdapter(fetch_error=AdapterRetryableError)
    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    assert len(results) == 2
    assert all(r.note is not None and r.note.startswith("fetch failed") for r in results)
    assert all(r.repaired is False for r in results)


@pytest.mark.integration
async def test_reconcile_repair_failure_not_marked_repaired(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Drift is found but the repair push fails → repaired stays False (the next
    run retries; reconciliation is idempotent)."""
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-rf", email="rec-rf@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(async_session_factory, tenant_id, channel_id, sku="RF-1", qty=10)

    # Channel drifts on BOTH stock (2 vs POS 10) and price (999 vs POS 500),
    # but every repair push raises — neither repair lands.
    adapter = _StubAdapter(
        snapshot=ChannelListingSnapshot(
            sku="RF-1",
            stock=2,
            price_minor=999,
            currency="AZN",
            external_listing_id="EXT-RF-1",
        ),
        push_error=AdapterRetryableError,
    )
    async with _scoped(async_session_factory, tenant_id) as session:
        channel = (
            await session.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one()
        results = await reconcile_channel(
            session, channel=channel, adapter=adapter, guard=_fast_guard()
        )

    r = results[0]
    assert r.stock_drift is True
    assert r.price_drift is True
    assert r.repaired is False
    assert adapter.pushes == []  # both pushes raised, nothing recorded


# ================================================================
# Tenant-level report
# ================================================================


@pytest.mark.integration
async def test_reconcile_tenant_reports_counts(
    migrated_db: None,
    async_session_factory: async_sessionmaker[AsyncSession],
    mock_adapter: tuple[MockMarketplaceAdapter, Any],
) -> None:
    """reconcile_tenant walks every active channel and aggregates the run: two
    listings, one drifted + repaired, one clean."""
    adapter, store = mock_adapter
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-t", email="rec-t@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(
        async_session_factory, tenant_id, channel_id, sku="T-DRIFT", qty=10, adapter=adapter
    )
    await _seed_listed_variant(
        async_session_factory, tenant_id, channel_id, sku="T-OK", qty=4, adapter=adapter
    )
    store.set_stock(seller_sku="T-DRIFT", qty=1)  # inject drift on one

    guard = _fast_guard()

    async def _factory(_channel: Channel) -> MockMarketplaceAdapter:
        return adapter

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await reconcile_tenant(session, adapter_factory=_factory, guard=guard)

    assert report.checked == 2
    assert report.drifted == 1
    assert report.repaired == 1
    assert store.listing_by_sku("T-DRIFT").stock == 10  # repaired
    assert store.listing_by_sku("T-OK").stock == 4  # untouched


@pytest.mark.integration
async def test_reconcile_tenant_skips_channel_without_registered_adapter(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A channel whose ``code`` has no registered adapter is skipped, not fatal —
    the cron keeps reconciling the channels that do have one."""
    tenant_id = await _seed_tenant(async_session_factory, subject="rec-na", email="rec-na@t.az")
    channel_id = await _seed_channel(async_session_factory, tenant_id)
    await _seed_listed_variant(async_session_factory, tenant_id, channel_id, sku="NA-1", qty=5)

    async def _factory(channel: Channel) -> Any:
        raise AdapterNotFoundError(f"no adapter for {channel.code}")

    async with _scoped(async_session_factory, tenant_id) as session:
        report = await reconcile_tenant(session, adapter_factory=_factory, guard=_fast_guard())

    assert report.checked == 0
    assert report.results == ()
