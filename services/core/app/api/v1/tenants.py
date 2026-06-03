"""Tenant onboarding API (AI-1.15) — ``POST /v1/tenants`` (super_admin only).

Onboarding creates a *new* tenant, so it runs cross-tenant: the ``super_admin``
gate means ``get_tenant_session`` yields the RLS-exempt owner session, under
which the new tenant + admin rows (any ``tenant_id``) are written.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import ConflictError

from ...domain.onboarding import onboard_tenant
from ..deps import get_tenant_session, requires_role

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantOnboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)  # ISO-3166-1 alpha-2
    plan: str = Field(default="free", min_length=1, max_length=50)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_subject: str = Field(min_length=1, max_length=255)  # Keycloak ``sub``

    @field_validator("country_code")
    @classmethod
    def _normalise_country(cls, value: str) -> str:
        return value.upper()

    @field_validator("admin_email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("admin_email must be an email address")
        return value.lower()


class TenantOnboardResponse(BaseModel):
    tenant_id: UUID
    admin_user_id: UUID
    name: str
    status: str


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantOnboardResponse)
async def onboard(
    body: TenantOnboardRequest,
    _admin: Principal = Depends(requires_role("super_admin")),
    session: AsyncSession = Depends(get_tenant_session),
) -> TenantOnboardResponse:
    try:
        result = await onboard_tenant(
            session,
            name=body.name,
            country_code=body.country_code,
            plan=body.plan,
            admin_email=body.admin_email,
            admin_subject=body.admin_subject,
        )
    except IntegrityError as exc:
        raise ConflictError("a user with this email or subject already exists") from exc
    return TenantOnboardResponse(
        tenant_id=result.tenant_id,
        admin_user_id=result.admin_user_id,
        name=result.name,
        status=result.status,
    )
