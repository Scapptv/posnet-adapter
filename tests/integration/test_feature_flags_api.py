"""AI-1.17 — feature flag CRUD (integration, real DB + RLS).

Handlers are awaited directly under an RLS-scoped session (this both exercises real
tenant isolation and lets coverage trace the post-await response build); gating is
checked through the full app, where it short-circuits before DB work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import NotFoundError
from services.core.app.api.deps import get_principal
from services.core.app.api.v1 import feature_flags as ff_api
from services.core.app.api.v1.feature_flags import FlagUpdateRequest
from services.core.app.config import Settings
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_ADMIN = Principal(
    subject="kc-ff-direct", username="a", email="a@x.io", roles=frozenset({"tenant_admin"})
)


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


def _as_map(response: ff_api.FlagsResponse) -> dict[str, bool]:
    return {flag.key: flag.enabled for flag in response.flags}


# ---- effective flags + overrides (handlers under a scoped session) ----


@pytest.mark.integration
async def test_list_returns_registry_defaults(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-ff-def", email="def@t.az")
    async with _scoped(async_session_factory, t1) as session:
        listed = await ff_api.list_(_tenant_id=t1, session=session)

    flags = _as_map(listed)
    assert flags["marketplace_sync"] is False  # gated-off default
    assert flags["multi_store"] is True  # on-by-default
    # the response also surfaces the built-in default alongside the effective value
    marketplace = next(f for f in listed.flags if f.key == "marketplace_sync")
    assert marketplace.default is False and marketplace.description


@pytest.mark.integration
async def test_override_then_upsert(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-ff-up", email="up@t.az")

    async with _scoped(async_session_factory, t1) as session:
        created = await ff_api.set_(
            "marketplace_sync",
            FlagUpdateRequest(enabled=True),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
        listed = await ff_api.list_(_tenant_id=t1, session=session)
    assert created.enabled is True
    assert _as_map(listed)["marketplace_sync"] is True  # override beats the False default

    async with _scoped(async_session_factory, t1) as session:  # fresh tx: update existing row
        updated = await ff_api.set_(
            "marketplace_sync",
            FlagUpdateRequest(enabled=False),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )
        listed = await ff_api.list_(_tenant_id=t1, session=session)
    assert updated.enabled is False
    assert _as_map(listed)["marketplace_sync"] is False  # upsert updated in place


@pytest.mark.integration
async def test_set_unknown_flag_is_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-ff-unk", email="unk@t.az")
    with pytest.raises(NotFoundError):
        async with _scoped(async_session_factory, t1) as session:
            await ff_api.set_(
                "does_not_exist",
                FlagUpdateRequest(enabled=True),
                _admin=_ADMIN,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_overrides_are_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-ff-i1", email="i1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-ff-i2", email="i2@t.az")

    async with _scoped(async_session_factory, t1) as session:
        await ff_api.set_(
            "marketplace_sync",
            FlagUpdateRequest(enabled=True),
            _admin=_ADMIN,
            tenant_id=t1,
            session=session,
        )

    async with _scoped(async_session_factory, t2) as session:
        listed = await ff_api.list_(_tenant_id=t2, session=session)
    assert _as_map(listed)["marketplace_sync"] is False  # t1's override is invisible to t2


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
def test_list_requires_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-ff-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.get("/v1/feature-flags")
    assert response.status_code == 403  # super_admin has no tenant context


@pytest.mark.integration
def test_set_forbidden_for_cashier(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-ff-cashier", ["cashier"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.put("/v1/feature-flags/marketplace_sync", json={"enabled": True})
    assert response.status_code == 403
