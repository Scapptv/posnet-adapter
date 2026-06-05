"""AI-2.7 — product publish + channels/listings read API (integration, RLS).

Handlers awaited directly under a scoped session (the test_catalog_api pattern):
real tenant isolation + post-await coverage. Publish flips the gate and re-emits
``catalog.variant.added`` so the dispatcher pushes; the channels endpoints surface
what the sync engine has written.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import NotFoundError
from services.core.app.api.v1 import catalog as cat
from services.core.app.api.v1 import channels as ch
from services.core.app.api.v1.catalog import ProductCreateRequest, VariantCreateRequest
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Channel, ChannelListing
from services.core.app.infrastructure.db.tenant import apply_tenant_scope

_MGR = Principal(subject="kc-pub", username="m", email="m@x.io", roles=frozenset({"store_manager"}))


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


async def _variant_added_count(session: AsyncSession, variant_id: UUID) -> int:
    return int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM outbox_events WHERE event_type = 'catalog.variant.added' "
                    "AND payload->>'variant_id' = :v"
                ),
                {"v": str(variant_id)},
            )
        ).scalar_one()
    )


# ---- publish / unpublish ----


@pytest.mark.integration
async def test_publish_sets_flag_and_reemits_variant_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pub-1", email="p1@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(name="P"), _w=_MGR, tenant_id=t1, session=session
        )
        variant = await cat.add_variant_(
            product.id,
            VariantCreateRequest(sku="S", base_price_minor=100),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        published = await cat.publish(product.id, _w=_MGR, tenant_id=t1, session=session)
        count = await _variant_added_count(session, variant.id)

    assert published.online_published is True
    # one variant.added from add_variant, one re-emitted on publish.
    assert count == 2


@pytest.mark.integration
async def test_unpublish_clears_flag(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pub-2", email="p2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(name="P"), _w=_MGR, tenant_id=t1, session=session
        )
        await cat.publish(product.id, _w=_MGR, tenant_id=t1, session=session)
        unpublished = await cat.unpublish(product.id, _w=_MGR, tenant_id=t1, session=session)

    assert unpublished.online_published is False


@pytest.mark.integration
async def test_publish_unknown_product_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pub-3", email="p3@t.az")
    with pytest.raises(NotFoundError):
        async with _scoped(async_session_factory, t1) as session:
            await cat.publish(uuid4(), _w=_MGR, tenant_id=t1, session=session)


# ---- channels + listings read ----


@pytest.mark.integration
async def test_list_channels_and_listings(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pub-4", email="p4@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(name="P"), _w=_MGR, tenant_id=t1, session=session
        )
        variant = await cat.add_variant_(
            product.id,
            VariantCreateRequest(sku="SKU-CH", base_price_minor=100),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        channel = Channel(tenant_id=t1, code="mock-marketplace", name="Mock", status="active")
        session.add(channel)
        await session.flush()
        session.add(
            ChannelListing(
                tenant_id=t1,
                channel_id=channel.id,
                variant_id=variant.id,
                external_listing_id="EXT-1",
                status="active",
            )
        )
        await session.flush()

        channels = await ch.list_channels(_r=_MGR, _tenant_id=t1, session=session)
        listings = await ch.list_channel_listings(_r=_MGR, _tenant_id=t1, session=session)

    assert [c.code for c in channels] == ["mock-marketplace"]
    assert len(listings) == 1
    assert listings[0].sku == "SKU-CH"
    assert listings[0].channel_code == "mock-marketplace"
    assert listings[0].external_listing_id == "EXT-1"
    assert listings[0].status == "active"


@pytest.mark.integration
async def test_channels_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pub-i1", email="pi1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-pub-i2", email="pi2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        session.add(Channel(tenant_id=t1, code="only-t1", name="T1", status="active"))
        await session.flush()

    async with _scoped(async_session_factory, t2) as session:
        channels = await ch.list_channels(_r=_MGR, _tenant_id=t2, session=session)
    assert all(c.code != "only-t1" for c in channels)
