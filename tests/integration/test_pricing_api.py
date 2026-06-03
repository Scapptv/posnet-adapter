"""AI-2.3 — pricing resolution + overrides (integration, real DB + RLS).

Handlers awaited directly under an RLS-scoped session; window-precision cases call
the domain ``resolve_price`` with an explicit ``at``. Gating via the full app.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import NotFoundError
from services.core.app.api.deps import get_principal
from services.core.app.api.v1 import pricing as pr
from services.core.app.api.v1.pricing import PriceOverrideCreateRequest
from services.core.app.config import Settings
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.domain.pricing import resolve_price, set_override
from services.core.app.infrastructure.db.models import Store
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_MGR = Principal(
    subject="kc-pr-mgr", username="m", email="m@x.io", roles=frozenset({"store_manager"})
)
_T0 = datetime(2026, 6, 1, tzinfo=UTC)
_MID = datetime(2026, 6, 15, tzinfo=UTC)
_END = datetime(2026, 7, 1, tzinfo=UTC)


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


async def _variant(session: AsyncSession, tenant_id: UUID, *, base: int = 100) -> UUID:
    product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
    variant = await add_variant(
        session, tenant_id=tenant_id, product_id=product.id, sku="S1", base_price_minor=base
    )
    return variant.id


# ---- resolution (handlers + domain) ----


@pytest.mark.integration
async def test_base_price_when_no_override(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-b", email="b@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1, base=250)
        resolved = await pr.price(
            variant_id, _r=_MGR, _tenant_id=t1, session=session
        )  # at=None -> now
    assert resolved.effective_price_minor == 250
    assert resolved.base_price_minor == 250
    assert resolved.source == "base"
    assert resolved.currency == "AZN"
    assert resolved.override_id is None


@pytest.mark.integration
async def test_tenant_override_applies(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-o", email="o@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1, base=100)
        created = await pr.create_override(
            variant_id,
            PriceOverrideCreateRequest(price_minor=80),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        resolved = await pr.price(variant_id, at=_MID, _r=_MGR, _tenant_id=t1, session=session)
    assert resolved.effective_price_minor == 80
    assert resolved.source == "override"
    assert resolved.override_id == created.id


@pytest.mark.integration
async def test_store_override_beats_tenant_wide(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-s", email="s@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1, base=100)
        store = Store(tenant_id=t1, name="S", timezone="Asia/Baku")
        session.add(store)
        await session.flush()
        store_id = store.id
        await set_override(
            session, tenant_id=t1, variant_id=variant_id, price_minor=80
        )  # tenant-wide
        await set_override(
            session, tenant_id=t1, variant_id=variant_id, price_minor=70, store_id=store_id
        )  # store-specific
        for_store = await resolve_price(session, variant_id=variant_id, at=_MID, store_id=store_id)
        for_other = await resolve_price(session, variant_id=variant_id, at=_MID, store_id=uuid4())
        no_store = await resolve_price(session, variant_id=variant_id, at=_MID)

    assert for_store.effective_price_minor == 70  # store-specific wins
    assert for_other.effective_price_minor == 80  # falls back to tenant-wide
    assert no_store.effective_price_minor == 80  # store-specific ignored without a store


@pytest.mark.integration
async def test_validity_window(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-w", email="w@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1, base=100)
        await set_override(
            session,
            tenant_id=t1,
            variant_id=variant_id,
            price_minor=60,
            valid_from=_T0,
            valid_to=_END,
        )
        before = await resolve_price(session, variant_id=variant_id, at=_T0 - timedelta(days=1))
        during = await resolve_price(session, variant_id=variant_id, at=_MID)
        after = await resolve_price(session, variant_id=variant_id, at=_END + timedelta(days=1))

    assert before.effective_price_minor == 100  # not yet active
    assert during.effective_price_minor == 60  # active
    assert after.effective_price_minor == 100  # expired


@pytest.mark.integration
async def test_override_unknown_variant_or_store_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-u", email="u@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        with pytest.raises(NotFoundError):  # unknown variant
            await set_override(session, tenant_id=t1, variant_id=uuid4(), price_minor=10)
        with pytest.raises(NotFoundError):  # unknown store
            await set_override(
                session, tenant_id=t1, variant_id=variant_id, price_minor=10, store_id=uuid4()
            )


@pytest.mark.integration
async def test_resolve_unknown_variant_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-r", email="r@t.az")
    with pytest.raises(NotFoundError):
        async with _scoped(async_session_factory, t1) as session:
            await pr.price(uuid4(), _r=_MGR, _tenant_id=t1, session=session)


@pytest.mark.integration
async def test_pricing_is_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-pr-i1", email="i1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-pr-i2", email="i2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1, base=100)
        await set_override(session, tenant_id=t1, variant_id=variant_id, price_minor=40)
    # t2 cannot even see the variant; its own resolve of that id is a 404, proving isolation.
    with pytest.raises(NotFoundError):
        async with _scoped(async_session_factory, t2) as session:
            await resolve_price(session, variant_id=variant_id, at=_MID)


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
def test_pricing_write_forbidden_for_cashier(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-pr-cashier", ["cashier"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post(f"/v1/variants/{uuid4()}/price-overrides", json={"price_minor": 50})
    assert response.status_code == 403  # cashier lacks pricing:write


@pytest.mark.integration
def test_pricing_requires_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-pr-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.get(f"/v1/variants/{uuid4()}/price")
    assert response.status_code == 403  # passes permission gate, no tenant
