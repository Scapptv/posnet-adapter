"""Role CRUD with permissions (AI-1.16) — tenant-scoped, ``tenant_admin`` only.

Roles + their permissions are per-tenant rows (the DB-driven RBAC data the static
``libs/auth`` map will eventually defer to). Reads/writes are RLS-scoped.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import ConflictError

from ...domain.identity import PermissionSpec, create_role, list_roles_with_permissions
from ..deps import get_tenant_session, require_tenant, requires_role

router = APIRouter(prefix="/roles", tags=["roles"])
_TENANT_ADMIN = requires_role("tenant_admin")


class PermissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)


class RoleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    permissions: list[PermissionModel] = Field(default_factory=list)


class RoleResponse(BaseModel):
    id: UUID
    name: str
    permissions: list[PermissionModel]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RoleResponse)
async def create(
    body: RoleCreateRequest,
    _admin: Principal = Depends(_TENANT_ADMIN),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> RoleResponse:
    specs = [PermissionSpec(resource=p.resource, action=p.action) for p in body.permissions]
    try:
        role = await create_role(session, tenant_id=tenant_id, name=body.name, permissions=specs)
    except IntegrityError as exc:
        raise ConflictError("a role with this name already exists") from exc
    return RoleResponse(id=role.id, name=role.name, permissions=body.permissions)


@router.get("", response_model=list[RoleResponse])
async def list_(
    _admin: Principal = Depends(_TENANT_ADMIN),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[RoleResponse]:
    return [
        RoleResponse(
            id=role.id,
            name=role.name,
            permissions=[PermissionModel(resource=s.resource, action=s.action) for s in specs],
        )
        for role, specs in await list_roles_with_permissions(session)
    ]
