"""Feature flag API (AI-1.17) — tenant-scoped.

``GET /v1/feature-flags`` returns the effective flags for the caller's tenant (any
tenant member, so the UI can adapt). ``PUT /v1/feature-flags/{key}`` upserts a
per-tenant override and is restricted to ``tenant_admin``. Both run under the
RLS-scoped session, so a tenant only ever sees/sets its own overrides.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import NotFoundError
from libs.feature_flags import UnknownFlagError

from ...domain.feature_flags import effective_flags, set_flag
from ...feature_flags import REGISTRY
from ..deps import get_tenant_session, require_tenant, requires_role

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])
_TENANT_ADMIN = requires_role("tenant_admin")


class FlagState(BaseModel):
    key: str
    enabled: bool  # effective value (default overlaid with the tenant override)
    default: bool  # built-in default
    description: str


class FlagsResponse(BaseModel):
    flags: list[FlagState]


class FlagUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class FlagResponse(BaseModel):
    key: str
    enabled: bool


@router.get("", response_model=FlagsResponse)
async def list_(
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> FlagsResponse:
    effective = await effective_flags(session, REGISTRY)
    return FlagsResponse(
        flags=[
            FlagState(
                key=spec.key,
                enabled=effective[spec.key],
                default=spec.default,
                description=spec.description,
            )
            for spec in REGISTRY.specs()
        ]
    )


@router.put("/{key}", response_model=FlagResponse)
async def set_(
    key: str,
    body: FlagUpdateRequest,
    _admin: Principal = Depends(_TENANT_ADMIN),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> FlagResponse:
    try:
        flag = await set_flag(
            session, tenant_id=tenant_id, key=key, enabled=body.enabled, registry=REGISTRY
        )
    except UnknownFlagError as exc:
        raise NotFoundError(f"unknown feature flag: {key}") from exc
    return FlagResponse(key=flag.key, enabled=flag.enabled)
