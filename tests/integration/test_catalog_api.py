"""AI-2.1 — catalog CRUD + POS lookup (integration, real DB + RLS).

Handlers are awaited directly under an RLS-scoped session (real tenant isolation +
post-await coverage); gating is checked through the full app where it short-circuits.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import ConflictError, NotFoundError, ValidationError
from services.core.app.api.deps import get_principal
from services.core.app.api.v1 import catalog as cat
from services.core.app.api.v1.catalog import ProductCreateRequest, VariantCreateRequest
from services.core.app.config import Settings
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Store
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_MGR = Principal(
    subject="kc-cat-mgr", username="m", email="m@x.io", roles=frozenset({"store_manager"})
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


# ---- CRUD + lookup (handlers under a scoped session) ----


@pytest.mark.integration
async def test_create_product_with_images_and_detail(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-a1", email="a1@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(
                name="Coca Cola",
                currency="azn",  # normalised to AZN
                brand="CC",
                category_path=["Drinks", "Soda"],
                image_urls=["http://img/1.png", "http://img/2.png"],
            ),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        detail = await cat.detail(product.id, _r=_MGR, _tenant_id=t1, session=session)

    assert product.currency == "AZN"
    assert detail.name == "Coca Cola"
    assert detail.category_path == ["Drinks", "Soda"]
    assert [i.url for i in detail.images] == ["http://img/1.png", "http://img/2.png"]
    assert detail.variants == []


@pytest.mark.integration
async def test_add_variant_and_pos_lookup(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-a2", email="a2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(name="Water"), _w=_MGR, tenant_id=t1, session=session
        )
        variant = await cat.add_variant_(
            product.id,
            VariantCreateRequest(
                sku="W-500", barcode="8690000000001", base_price_minor=150, name="500ml"
            ),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        by_bc = await cat.lookup(barcode="8690000000001", _r=_MGR, _tenant_id=t1, session=session)
        by_sku = await cat.lookup(sku="W-500", _r=_MGR, _tenant_id=t1, session=session)

    assert variant.sku == "W-500"
    assert by_bc.id == variant.id
    assert by_sku.id == variant.id
    assert by_bc.base_price_minor == 150


@pytest.mark.integration
async def test_lookup_validation_and_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-a3", email="a3@t.az")
    async with _scoped(async_session_factory, t1) as session:
        with pytest.raises(ValidationError):  # neither
            await cat.lookup(_r=_MGR, _tenant_id=t1, session=session)
        with pytest.raises(ValidationError):  # both
            await cat.lookup(barcode="x", sku="y", _r=_MGR, _tenant_id=t1, session=session)
        with pytest.raises(NotFoundError):  # barcode miss
            await cat.lookup(barcode="nope", _r=_MGR, _tenant_id=t1, session=session)
        with pytest.raises(NotFoundError):  # sku miss
            await cat.lookup(sku="nope", _r=_MGR, _tenant_id=t1, session=session)


@pytest.mark.integration
async def test_list_products_full_text_search(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-a4", email="a4@t.az")
    async with _scoped(async_session_factory, t1) as session:
        await cat.create(
            ProductCreateRequest(name="Coca Cola"), _w=_MGR, tenant_id=t1, session=session
        )
        await cat.create(ProductCreateRequest(name="Pepsi"), _w=_MGR, tenant_id=t1, session=session)
        hits = await cat.list_(
            response=Response(), q="cola", _r=_MGR, _tenant_id=t1, session=session
        )
        every = await cat.list_(response=Response(), _r=_MGR, _tenant_id=t1, session=session)

    assert {p.name for p in hits} == {"Coca Cola"}
    assert {p.name for p in every} == {"Coca Cola", "Pepsi"}


@pytest.mark.integration
async def test_list_products_pagination(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """limit/offset page over a stable order; X-Total-Count carries the full
    count regardless of the page window."""
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-pg", email="pg@t.az")
    async with _scoped(async_session_factory, t1) as session:
        for n in ("P1", "P2", "P3", "P4", "P5"):
            await cat.create(ProductCreateRequest(name=n), _w=_MGR, tenant_id=t1, session=session)

        page1_resp = Response()
        page1 = await cat.list_(
            response=page1_resp, limit=2, offset=0, _r=_MGR, _tenant_id=t1, session=session
        )
        page2 = await cat.list_(
            response=Response(), limit=2, offset=2, _r=_MGR, _tenant_id=t1, session=session
        )

    assert [p.name for p in page1] == ["P1", "P2"]  # stable ORDER BY name, id
    assert [p.name for p in page2] == ["P3", "P4"]
    assert page1_resp.headers["X-Total-Count"] == "5"  # full count, not the page size


@pytest.mark.integration
async def test_duplicate_sku_conflicts(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-a5", email="a5@t.az")
    async with _scoped(async_session_factory, t1) as session:
        product = await cat.create(
            ProductCreateRequest(name="P"), _w=_MGR, tenant_id=t1, session=session
        )
        await cat.add_variant_(
            product.id,
            VariantCreateRequest(sku="DUP", base_price_minor=100),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
    product_id = product.id

    with pytest.raises(ConflictError):  # fresh tx so the failed insert rolls back
        async with _scoped(async_session_factory, t1) as session:
            await cat.add_variant_(
                product_id,
                VariantCreateRequest(sku="DUP", base_price_minor=200),
                _w=_MGR,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_catalog_is_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-i1", email="i1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-cat-i2", email="i2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p1 = await cat.create(
            ProductCreateRequest(name="T1 Only"), _w=_MGR, tenant_id=t1, session=session
        )
    p1_id = p1.id

    async with _scoped(async_session_factory, t2) as session:
        listed = await cat.list_(response=Response(), _r=_MGR, _tenant_id=t2, session=session)
        with pytest.raises(NotFoundError):  # t1's product invisible under t2 RLS
            await cat.detail(p1_id, _r=_MGR, _tenant_id=t2, session=session)
    assert all(p.name != "T1 Only" for p in listed)


@pytest.mark.integration
async def test_add_variant_to_other_tenant_product_is_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-x1", email="x1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-cat-x2", email="x2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p1 = await cat.create(
            ProductCreateRequest(name="X"), _w=_MGR, tenant_id=t1, session=session
        )
    p1_id = p1.id

    with pytest.raises(NotFoundError):  # t1's product not visible -> can't attach a variant
        async with _scoped(async_session_factory, t2) as session:
            await cat.add_variant_(
                p1_id,
                VariantCreateRequest(sku="S", base_price_minor=1),
                _w=_MGR,
                tenant_id=t2,
                session=session,
            )


@pytest.mark.integration
async def test_product_store_must_belong_to_tenant(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-cat-s1", email="s1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-cat-s2", email="s2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store = Store(tenant_id=t1, name="Main", timezone="Asia/Baku")
        session.add(store)
        await session.flush()
        store_id = store.id
        ok = await cat.create(
            ProductCreateRequest(name="Shelf", store_id=store_id),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
    assert ok.store_id == store_id

    with pytest.raises(NotFoundError):  # t1's store invisible to t2
        async with _scoped(async_session_factory, t2) as session:
            await cat.create(
                ProductCreateRequest(name="Bad", store_id=store_id),
                _w=_MGR,
                tenant_id=t2,
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
def test_catalog_write_forbidden_for_cashier(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-cat-cashier", ["cashier"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post("/v1/products", json={"name": "X"})
    assert response.status_code == 403  # cashier has catalog:read but not catalog:write


@pytest.mark.integration
def test_catalog_requires_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-cat-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.get("/v1/products")
    assert response.status_code == 403  # super_admin passes the permission gate but has no tenant
