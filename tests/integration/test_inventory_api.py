"""AI-2.2 — inventory movements + anti-oversell (integration, real DB + RLS).

Handlers awaited directly under an RLS-scoped session; conflict cases use a fresh
transaction (the failed movement raises before any write). Gating via the full app.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal
from libs.common import ConflictError, NotFoundError, ValidationError
from services.core.app.api.deps import get_principal
from services.core.app.api.v1 import inventory as inv
from services.core.app.api.v1.inventory import MovementRequest, WarehouseCreateRequest
from services.core.app.config import Settings
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.inventory import create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_MGR = Principal(
    subject="kc-inv-mgr", username="m", email="m@x.io", roles=frozenset({"store_manager"})
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


async def _variant(session: AsyncSession, tenant_id: UUID, *, sku: str = "S1") -> UUID:
    product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
    variant = await add_variant(
        session, tenant_id=tenant_id, product_id=product.id, sku=sku, base_price_minor=100
    )
    return variant.id


def _move(
    variant_id: UUID, warehouse_id: UUID, kind: str, qty: int, **kw: object
) -> MovementRequest:
    return MovementRequest(
        variant_id=variant_id, warehouse_id=warehouse_id, kind=kind, qty=qty, **kw
    )


# ---- warehouses ----


@pytest.mark.integration
async def test_warehouse_create_and_list(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-w", email="w@t.az")
    async with _scoped(async_session_factory, t1) as session:
        wh = await inv.create_warehouse_(
            WarehouseCreateRequest(name="Main", type="central"),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
        listed = await inv.list_warehouses_(_r=_MGR, _tenant_id=t1, session=session)
    assert wh.name == "Main" and wh.type == "central"
    assert [w.name for w in listed] == ["Main"]


# ---- movement flow + anti-oversell ----


@pytest.mark.integration
async def test_receive_reserve_unreserve_out(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-f", email="f@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id

        received = await inv.move(
            _move(variant_id, wh_id, "in", 10), _w=_MGR, tenant_id=t1, session=session
        )
        reserved = await inv.move(
            _move(variant_id, wh_id, "reserve", 7), _w=_MGR, tenant_id=t1, session=session
        )
        unreserved = await inv.move(
            _move(variant_id, wh_id, "unreserve", 3), _w=_MGR, tenant_id=t1, session=session
        )
        shipped = await inv.move(
            _move(variant_id, wh_id, "out", 5), _w=_MGR, tenant_id=t1, session=session
        )

    assert (received.qty, received.available, received.version) == (10, 10, 1)
    assert (reserved.reserved_qty, reserved.available) == (7, 3)
    assert unreserved.reserved_qty == 4
    assert (shipped.qty, shipped.reserved_qty, shipped.available, shipped.version) == (5, 4, 1, 4)


@pytest.mark.integration
async def test_reserve_beyond_available_is_rejected(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-os", email="os@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
        await inv.move(_move(variant_id, wh_id, "in", 10), _w=_MGR, tenant_id=t1, session=session)
        await inv.move(
            _move(variant_id, wh_id, "reserve", 7), _w=_MGR, tenant_id=t1, session=session
        )

    with pytest.raises(ConflictError):  # available 3 < 5 -> anti-oversell
        async with _scoped(async_session_factory, t1) as session:
            await inv.move(
                _move(variant_id, wh_id, "reserve", 5), _w=_MGR, tenant_id=t1, session=session
            )


@pytest.mark.integration
async def test_out_beyond_available_is_rejected(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-o2", email="o2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
        await inv.move(_move(variant_id, wh_id, "in", 5), _w=_MGR, tenant_id=t1, session=session)
        await inv.move(
            _move(variant_id, wh_id, "reserve", 4), _w=_MGR, tenant_id=t1, session=session
        )

    with pytest.raises(ConflictError):  # available 1 < 2
        async with _scoped(async_session_factory, t1) as session:
            await inv.move(
                _move(variant_id, wh_id, "out", 2), _w=_MGR, tenant_id=t1, session=session
            )


@pytest.mark.integration
async def test_adjust_signed_and_below_reserved(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-adj", email="adj@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
        await inv.move(
            _move(variant_id, wh_id, "adjust", 10), _w=_MGR, tenant_id=t1, session=session
        )  # creates row
        down = await inv.move(
            _move(variant_id, wh_id, "adjust", -3), _w=_MGR, tenant_id=t1, session=session
        )
        await inv.move(
            _move(variant_id, wh_id, "reserve", 5), _w=_MGR, tenant_id=t1, session=session
        )
    assert down.qty == 7

    with pytest.raises(ValidationError):  # 7 - 6 = 1 < reserved 5
        async with _scoped(async_session_factory, t1) as session:
            await inv.move(
                _move(variant_id, wh_id, "adjust", -6), _w=_MGR, tenant_id=t1, session=session
            )


@pytest.mark.integration
async def test_out_without_stock_level_is_invalid(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-ns", email="ns@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
    with pytest.raises(ValidationError):  # no inventory row yet -> can't remove
        async with _scoped(async_session_factory, t1) as session:
            await inv.move(
                _move(variant_id, wh_id, "out", 1), _w=_MGR, tenant_id=t1, session=session
            )


@pytest.mark.integration
async def test_optimistic_version_check(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-v", email="v@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
        await inv.move(
            _move(variant_id, wh_id, "in", 10), _w=_MGR, tenant_id=t1, session=session
        )  # version 1

    async with _scoped(async_session_factory, t1) as session:  # correct version proceeds
        ok = await inv.move(
            _move(variant_id, wh_id, "in", 5, expected_version=1),
            _w=_MGR,
            tenant_id=t1,
            session=session,
        )
    assert ok.version == 2

    with pytest.raises(ConflictError):  # stale version rejected
        async with _scoped(async_session_factory, t1) as session:
            await inv.move(
                _move(variant_id, wh_id, "in", 1, expected_version=1),
                _w=_MGR,
                tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_levels_across_warehouses(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-lv", email="lv@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        w1 = (await create_warehouse(session, tenant_id=t1, name="A", type_="store")).id
        w2 = (await create_warehouse(session, tenant_id=t1, name="B", type_="store")).id
        await inv.move(_move(variant_id, w1, "in", 4), _w=_MGR, tenant_id=t1, session=session)
        await inv.move(_move(variant_id, w2, "in", 6), _w=_MGR, tenant_id=t1, session=session)
        levels = await inv.levels(variant_id, _r=_MGR, _tenant_id=t1, session=session)
    assert sorted(level.qty for level in levels) == [4, 6]


@pytest.mark.integration
async def test_unknown_variant_or_warehouse_not_found(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-u", email="u@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="W", type_="store")).id
        with pytest.raises(NotFoundError):  # variant from nowhere (cross-tenant reduces to this)
            await inv.move(_move(uuid4(), wh_id, "in", 1), _w=_MGR, tenant_id=t1, session=session)
        with pytest.raises(NotFoundError):  # warehouse from nowhere
            await inv.move(
                _move(variant_id, uuid4(), "in", 1), _w=_MGR, tenant_id=t1, session=session
            )


@pytest.mark.integration
async def test_inventory_is_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="kc-inv-i1", email="i1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="kc-inv-i2", email="i2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        variant_id = await _variant(session, t1)
        wh_id = (await create_warehouse(session, tenant_id=t1, name="T1WH", type_="store")).id
        await inv.move(_move(variant_id, wh_id, "in", 9), _w=_MGR, tenant_id=t1, session=session)

    async with _scoped(async_session_factory, t2) as session:
        t2_levels = await inv.levels(variant_id, _r=_MGR, _tenant_id=t2, session=session)
        t2_warehouses = await inv.list_warehouses_(_r=_MGR, _tenant_id=t2, session=session)
    assert t2_levels == []  # t1's stock invisible
    assert all(w.name != "T1WH" for w in t2_warehouses)


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
def test_inventory_write_forbidden_for_cashier(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-inv-cashier", ["cashier"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post("/v1/warehouses", json={"name": "X"})
    assert response.status_code == 403  # cashier has inventory:read but not inventory:write


@pytest.mark.integration
def test_inventory_requires_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-inv-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.get("/v1/warehouses")
    assert response.status_code == 403  # passes permission gate, no tenant
