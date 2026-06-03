"""AI-1.16 — user/role CRUD + assignment (integration, real DB + RLS).

The handlers are awaited directly under an RLS-scoped session: this both exercises
real tenant isolation and lets coverage trace the post-await response build (the
FastAPI/greenlet path drops those lines). Gating is checked through the full app,
where it short-circuits before any DB work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import ConflictError, NotFoundError
from services.core.app.api.deps import get_principal
from services.core.app.api.v1 import roles as roles_api
from services.core.app.api.v1 import users as users_api
from services.core.app.api.v1.roles import RoleCreateRequest
from services.core.app.api.v1.users import AssignRoleRequest, UserCreateRequest
from services.core.app.config import Settings
from services.core.app.domain.identity import create_role
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_ADMIN = Principal(
    subject="kc-direct", username="a", email="a@x.io", roles=frozenset({"tenant_admin"})
)
_PERMS = [{"resource": "catalog", "action": "write"}]


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


# ---- CRUD + RLS (handlers called directly under a scoped session) ----


@pytest.mark.integration
async def test_create_and_list_users_are_tenant_scoped(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-id-a1", email="admin1@t.az")
    await _seed_tenant(async_session_factory, subject="kc-id-a2", email="admin2@t.az")

    async with _scoped(async_session_factory, t1) as session:
        created = await users_api.create(
            UserCreateRequest(email="New1@T.AZ", external_subject="kc-id-new1"),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
        listed = await users_api.list_(_admin=_ADMIN, _tenant_id=t1, session=session)

    assert created.email == "new1@t.az"
    assert created.status == "active"
    emails = {user.email for user in listed}
    assert {"admin1@t.az", "new1@t.az"} <= emails
    assert "admin2@t.az" not in emails  # RLS hides the other tenant


@pytest.mark.integration
async def test_create_user_duplicate_email_conflicts(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-id-dup", email="dup-admin@t.az")
    async with _scoped(async_session_factory, t1) as session:
        await users_api.create(
            UserCreateRequest(email="same@t.az", external_subject="kc-id-d1"),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )

    with pytest.raises(ConflictError):  # fresh tx so the failed insert rolls back cleanly
        async with _scoped(async_session_factory, t1) as session:
            await users_api.create(
                UserCreateRequest(email="same@t.az", external_subject="kc-id-d2"),
                _admin=_ADMIN,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_role_create_list_and_duplicate(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-id-role", email="role-admin@t.az")
    async with _scoped(async_session_factory, t1) as session:
        role = await roles_api.create(
            RoleCreateRequest(name="manager", permissions=_PERMS),  # type: ignore[arg-type]
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
        listed = await roles_api.list_(_admin=_ADMIN, _tenant_id=t1, session=session)

    assert role.name == "manager"
    assert [p.model_dump() for p in role.permissions] == _PERMS
    manager = next(r for r in listed if r.name == "manager")
    assert [p.model_dump() for p in manager.permissions] == _PERMS  # round-trips via the DB

    with pytest.raises(ConflictError):
        async with _scoped(async_session_factory, t1) as session:
            await roles_api.create(
                RoleCreateRequest(name="manager"),
                _admin=_ADMIN,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_assign_role_to_user(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-id-asg", email="asg-admin@t.az")
    store_id = uuid4()
    async with _scoped(async_session_factory, t1) as session:
        user = await users_api.create(
            UserCreateRequest(email="asgu@t.az", external_subject="kc-id-asgu"),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
        role = await roles_api.create(
            RoleCreateRequest(name="staff"), _admin=_ADMIN, tenant_id=t1, session=session
        )
        assignment = await users_api.assign(
            user.id,
            AssignRoleRequest(role_id=role.id, store_id=store_id),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )

    assert assignment.user_id == user.id
    assert assignment.role_id == role.id
    assert assignment.store_id == store_id
    user_id, role_id = user.id, role.id

    with pytest.raises(ConflictError):  # same (user, role, store) again -> unique violation
        async with _scoped(async_session_factory, t1) as session:
            await users_api.assign(
                user_id,
                AssignRoleRequest(role_id=role_id, store_id=store_id),
                _admin=_ADMIN,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_assign_role_from_another_tenant_is_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-id-xt1", email="xt1-admin@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-id-xt2", email="xt2-admin@t.az")
    async with async_session_factory() as session, session.begin():
        other_role = await create_role(session, tenant_id=t2, name="t2-role", permissions=[])
    other_role_id = other_role.id

    async with _scoped(async_session_factory, t1) as session:
        user = await users_api.create(
            UserCreateRequest(email="xt1u@t.az", external_subject="kc-id-xt1u"),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
    user_id = user.id

    with pytest.raises(NotFoundError):  # tenant2's role is invisible under tenant1 RLS
        async with _scoped(async_session_factory, t1) as session:
            await users_api.assign(
                user_id,
                AssignRoleRequest(role_id=other_role_id),
                _admin=_ADMIN,
                tenant_id=t1,
                session=session,
            )


# ---- gating (through the full app) ----


def _gated_app(subject: str, roles: list[str], pg_url: str, redis_url: str) -> object:
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_url,
            redis_url=redis_url,
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        )
    )
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject=subject, username="u", email="u@x.io", roles=frozenset(roles)
    )
    return app


@pytest.mark.integration
def test_identity_endpoints_forbidden_for_cashier(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-id-cashier", ["cashier"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post(
            "/v1/users", json={"email": "x@t.az", "external_subject": "kc-id-cx"}
        )
    assert response.status_code == 403


@pytest.mark.integration
def test_identity_endpoints_require_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-id-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post(
            "/v1/users", json={"email": "x@t.az", "external_subject": "kc-id-sx"}
        )
    assert response.status_code == 403  # super_admin has no tenant context
