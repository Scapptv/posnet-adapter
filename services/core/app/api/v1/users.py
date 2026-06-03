"""User CRUD + role assignment (AI-1.16) — tenant-scoped, ``tenant_admin`` only.

All three depend on ``require_tenant`` + ``get_tenant_session``, so they operate
strictly within the caller's tenant: reads are RLS-scoped, the create's
``tenant_id`` is the caller's (RLS ``WITH CHECK`` enforces it), and a system
principal without a tenant is rejected (403).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import ConflictError

from ...domain.identity import assign_role, create_user, list_users
from ..deps import get_tenant_session, require_tenant, requires_role

router = APIRouter(prefix="/users", tags=["users"])
_TENANT_ADMIN = requires_role("tenant_admin")


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    external_subject: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("email must be an email address")
        return value.lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str | None
    status: str
    external_subject: str | None


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: UUID
    store_id: UUID | None = None


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role_id: UUID
    store_id: UUID | None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create(
    body: UserCreateRequest,
    _admin: Principal = Depends(_TENANT_ADMIN),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> UserResponse:
    try:
        user = await create_user(
            session,
            tenant_id=tenant_id,
            email=body.email,
            external_subject=body.external_subject,
            phone=body.phone,
        )
    except IntegrityError as exc:
        raise ConflictError("a user with this email or subject already exists") from exc
    return UserResponse.model_validate(user)


@router.get("", response_model=list[UserResponse])
async def list_(
    _admin: Principal = Depends(_TENANT_ADMIN),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[UserResponse]:
    return [UserResponse.model_validate(user) for user in await list_users(session)]


@router.post(
    "/{user_id}/roles", status_code=status.HTTP_201_CREATED, response_model=AssignmentResponse
)
async def assign(
    user_id: UUID,
    body: AssignRoleRequest,
    _admin: Principal = Depends(_TENANT_ADMIN),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> AssignmentResponse:
    try:
        assignment = await assign_role(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=body.role_id,
            store_id=body.store_id,
        )
    except IntegrityError as exc:
        raise ConflictError("this role assignment already exists") from exc
    return AssignmentResponse.model_validate(assignment)
