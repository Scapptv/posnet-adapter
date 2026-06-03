"""Pricing API (AI-2.3) — effective price resolution + per-variant overrides.

Reads need ``pricing:read``, writes ``pricing:write`` (both store_manager /
tenant_admin). The POS sale flow (AI-2.5) resolves the sell price server-side, so
cashiers price via the sale, not this endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal

from ...domain.pricing import resolve_price, set_override
from ..deps import get_tenant_session, require_tenant, requires_permission

router = APIRouter(tags=["pricing"])
_READ = requires_permission("pricing", "read")
_WRITE = requires_permission("pricing", "write")


# ---- schemas ----


class PriceOverrideCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_minor: int = Field(ge=0)
    store_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to")
        return self


class PriceOverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    store_id: UUID | None
    price_minor: int
    valid_from: datetime | None
    valid_to: datetime | None


class ResolvedPriceResponse(BaseModel):
    variant_id: UUID
    currency: str
    base_price_minor: int
    effective_price_minor: int
    source: str  # "base" | "override"
    override_id: UUID | None


# ---- endpoints ----


@router.post(
    "/variants/{variant_id}/price-overrides",
    status_code=status.HTTP_201_CREATED,
    response_model=PriceOverrideResponse,
)
async def create_override(
    variant_id: UUID,
    body: PriceOverrideCreateRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> PriceOverrideResponse:
    override = await set_override(
        session,
        tenant_id=tenant_id,
        variant_id=variant_id,
        price_minor=body.price_minor,
        store_id=body.store_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
    )
    return PriceOverrideResponse.model_validate(override)


@router.get("/variants/{variant_id}/price", response_model=ResolvedPriceResponse)
async def price(
    variant_id: UUID,
    store_id: UUID | None = None,
    at: datetime | None = None,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ResolvedPriceResponse:
    resolved = await resolve_price(
        session, variant_id=variant_id, at=at or datetime.now(UTC), store_id=store_id
    )
    return ResolvedPriceResponse(
        variant_id=resolved.variant_id,
        currency=resolved.currency,
        base_price_minor=resolved.base_price_minor,
        effective_price_minor=resolved.effective_price_minor,
        source=resolved.source,
        override_id=resolved.override_id,
    )
