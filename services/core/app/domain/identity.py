"""Tenant-scoped identity management (AI-1.16).

CRUD over users, roles (+ their permissions) and role assignments. Every function
runs under the caller's RLS-scoped session (``posnet_app`` + ``app.current_tenant``):
reads see only the tenant's rows, and the RLS ``WITH CHECK`` rejects writes for
another tenant. ``tenant_id`` is passed explicitly for inserts — it must equal the
scoped tenant, which RLS enforces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import NotFoundError

from ..infrastructure.db.models import Permission, Role, User, UserRole


@dataclass(frozen=True)
class PermissionSpec:
    resource: str
    action: str


async def create_user(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    email: str,
    external_subject: str | None,
    phone: str | None,
) -> User:
    user = User(tenant_id=tenant_id, email=email, external_subject=external_subject, phone=phone)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def list_users(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.email))
    return result.scalars().all()


async def create_role(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    permissions: Sequence[PermissionSpec],
) -> Role:
    role = Role(tenant_id=tenant_id, name=name)
    session.add(role)
    await session.flush()  # assigns role.id
    for spec in permissions:
        session.add(
            Permission(
                tenant_id=tenant_id, role_id=role.id, resource=spec.resource, action=spec.action
            )
        )
    await session.flush()
    await session.refresh(role)
    return role


async def list_roles_with_permissions(
    session: AsyncSession,
) -> list[tuple[Role, list[PermissionSpec]]]:
    roles = (await session.execute(select(Role).order_by(Role.name))).scalars().all()
    permissions = (await session.execute(select(Permission))).scalars().all()
    by_role: dict[UUID, list[PermissionSpec]] = {}
    for perm in permissions:
        by_role.setdefault(perm.role_id, []).append(PermissionSpec(perm.resource, perm.action))
    return [(role, by_role.get(role.id, [])) for role in roles]


async def assign_role(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    role_id: UUID,
    store_id: UUID | None = None,
) -> UserRole:
    # Both lookups are RLS-scoped, so a foreign id from another tenant reads as
    # missing — this is what stops a tenant assigning across the boundary (the FK
    # alone would accept any existing id).
    user = (await session.execute(select(User.id).where(User.id == user_id))).first()
    role = (await session.execute(select(Role.id).where(Role.id == role_id))).first()
    if user is None or role is None:
        raise NotFoundError("user or role not found in this tenant")

    assignment = UserRole(tenant_id=tenant_id, user_id=user_id, role_id=role_id, store_id=store_id)
    session.add(assignment)
    await session.flush()
    return assignment
