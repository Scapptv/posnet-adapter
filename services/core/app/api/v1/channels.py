"""Channels + listings read API (AI-2.7) — sync visibility for the merchant.

Read-only views so the admin panel can show which channels are connected and
what's been pushed to them: the sync engine writes ``channel_listings`` (external
id, status, last_synced_at), this just surfaces them joined to the SKU. All
tenant-scoped via the RLS session.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal

from ...infrastructure.db.models import Channel, ChannelListing, Variant
from ..deps import get_tenant_session, require_tenant, requires_permission

router = APIRouter(tags=["channels"])
_READ = requires_permission("catalog", "read")


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    status: str


class ChannelListingResponse(BaseModel):
    channel_id: UUID
    channel_code: str
    variant_id: UUID
    sku: str
    external_listing_id: str | None
    status: str
    last_synced_at: datetime | None


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ChannelResponse]:
    channels = (await session.execute(select(Channel).order_by(Channel.code))).scalars().all()
    return [ChannelResponse.model_validate(c) for c in channels]


@router.get("/channel-listings", response_model=list[ChannelListingResponse])
async def list_channel_listings(
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ChannelListingResponse]:
    """Every channel listing in the tenant (what the sync engine has pushed),
    joined to its channel code + SKU for display."""
    rows = (
        await session.execute(
            select(ChannelListing, Channel.code, Variant.sku)
            .join(Channel, ChannelListing.channel_id == Channel.id)
            .join(Variant, ChannelListing.variant_id == Variant.id)
            .order_by(Channel.code, Variant.sku)
        )
    ).all()
    return [
        ChannelListingResponse(
            channel_id=listing.channel_id,
            channel_code=code,
            variant_id=listing.variant_id,
            sku=sku,
            external_listing_id=listing.external_listing_id,
            status=listing.status,
            last_synced_at=listing.last_synced_at,
        )
        for listing, code, sku in rows
    ]
