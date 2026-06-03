"""AI-2.4 — shifts/vardiya + cash management (integration, real DB + RLS).

Handlers awaited directly under an RLS-scoped session; conflict/closed cases use a
fresh transaction. The onboarded admin user serves as the cashier. Gating via the app.
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
from services.core.app.api.v1 import shifts as sh
from services.core.app.api.v1.shifts import CashMovementRequest, CloseShiftRequest, OpenShiftRequest
from services.core.app.config import Settings
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Store
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.main import create_app

_CASHIER = Principal(
    subject="kc-sh-cashier", username="c", email="c@x.io", roles=frozenset({"cashier"})
)


async def _seed_tenant(
    factory: async_sessionmaker[AsyncSession], *, subject: str, email: str
) -> tuple[UUID, UUID]:
    """Returns (tenant_id, admin_user_id); the admin doubles as the cashier."""
    async with factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="T",
            country_code="AZ",
            plan="free",
            admin_email=email,
            admin_subject=subject,
        )
    return result.tenant_id, result.admin_user_id


@asynccontextmanager
async def _scoped(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    async with factory() as session, session.begin():
        await apply_tenant_scope(session, tenant_id)
        yield session


async def _store(session: AsyncSession, tenant_id: UUID) -> UUID:
    store = Store(tenant_id=tenant_id, name="S", timezone="Asia/Baku")
    session.add(store)
    await session.flush()
    return store.id


def _open(store_id: UUID, cashier_id: UUID, cash: int = 10000) -> OpenShiftRequest:
    return OpenShiftRequest(store_id=store_id, cashier_id=cashier_id, opening_cash_minor=cash)


# ---- open / detail / cash ----


@pytest.mark.integration
async def test_open_and_detail(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-a", email="a@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        shift = await sh.open_(
            OpenShiftRequest(
                store_id=store_id, cashier_id=cashier, opening_cash_minor=10000, currency="azn"
            ),
            _w=_CASHIER,
            tenant_id=t1,
            session=session,
        )
        detail = await sh.detail(shift.id, _r=_CASHIER, _tenant_id=t1, session=session)
    assert shift.status == "open" and shift.currency == "AZN" and shift.opening_cash_minor == 10000
    assert (detail.cash_in_minor, detail.cash_out_minor, detail.expected_cash_minor) == (
        0,
        0,
        10000,
    )


@pytest.mark.integration
async def test_cash_movements_summary(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-c", email="c@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        shift = await sh.open_(_open(store_id, cashier), _w=_CASHIER, tenant_id=t1, session=session)
        await sh.cash(
            shift.id,
            CashMovementRequest(kind="in", amount_minor=5000, reason="float"),
            _w=_CASHIER,
            tenant_id=t1,
            session=session,
        )
        await sh.cash(
            shift.id,
            CashMovementRequest(kind="out", amount_minor=2000),
            _w=_CASHIER,
            tenant_id=t1,
            session=session,
        )
        detail = await sh.detail(shift.id, _r=_CASHIER, _tenant_id=t1, session=session)
    assert (detail.cash_in_minor, detail.cash_out_minor) == (5000, 2000)
    assert detail.expected_cash_minor == 13000  # 10000 + 5000 - 2000


@pytest.mark.integration
async def test_double_open_conflicts(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-d", email="d@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        await sh.open_(_open(store_id, cashier), _w=_CASHIER, tenant_id=t1, session=session)

    with pytest.raises(ConflictError):  # one open shift per (store, cashier)
        async with _scoped(async_session_factory, t1) as session:
            await sh.open_(_open(store_id, cashier), _w=_CASHIER, tenant_id=t1, session=session)


@pytest.mark.integration
async def test_close_then_record_and_reclose_fail(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-cl", email="cl@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        shift = await sh.open_(_open(store_id, cashier), _w=_CASHIER, tenant_id=t1, session=session)
        closed = await sh.close_(
            shift.id,
            CloseShiftRequest(closing_cash_minor=9500),
            _w=_CASHIER,
            _tenant_id=t1,
            session=session,
        )
    assert (
        closed.status == "closed"
        and closed.closing_cash_minor == 9500
        and closed.closed_at is not None
    )
    shift_id = shift.id

    with pytest.raises(ValidationError):  # no cash on a closed shift
        async with _scoped(async_session_factory, t1) as session:
            await sh.cash(
                shift_id,
                CashMovementRequest(kind="in", amount_minor=100),
                _w=_CASHIER,
                tenant_id=t1,
                session=session,
            )
    with pytest.raises(ConflictError):  # already closed
        async with _scoped(async_session_factory, t1) as session:
            await sh.close_(
                shift_id,
                CloseShiftRequest(closing_cash_minor=9000),
                _w=_CASHIER,
                _tenant_id=t1,
                session=session,
            )


@pytest.mark.integration
async def test_unknown_shift_and_open_targets(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-u", email="u@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        with pytest.raises(NotFoundError):
            await sh.detail(uuid4(), _r=_CASHIER, _tenant_id=t1, session=session)
        with pytest.raises(NotFoundError):
            await sh.close_(
                uuid4(),
                CloseShiftRequest(closing_cash_minor=0),
                _w=_CASHIER,
                _tenant_id=t1,
                session=session,
            )
        with pytest.raises(NotFoundError):
            await sh.cash(
                uuid4(),
                CashMovementRequest(kind="in", amount_minor=1),
                _w=_CASHIER,
                tenant_id=t1,
                session=session,
            )
        with pytest.raises(NotFoundError):  # unknown store
            await sh.open_(_open(uuid4(), cashier), _w=_CASHIER, tenant_id=t1, session=session)
        with pytest.raises(NotFoundError):  # unknown cashier
            await sh.open_(_open(store_id, uuid4()), _w=_CASHIER, tenant_id=t1, session=session)


@pytest.mark.integration
async def test_list_filters(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, cashier = await _seed_tenant(async_session_factory, subject="kc-sh-l", email="l@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        await sh.open_(_open(store_id, cashier), _w=_CASHIER, tenant_id=t1, session=session)
        every = await sh.list_(_r=_CASHIER, _tenant_id=t1, session=session)
        by_store = await sh.list_(store_id=store_id, _r=_CASHIER, _tenant_id=t1, session=session)
        open_only = await sh.list_(status_="open", _r=_CASHIER, _tenant_id=t1, session=session)
        closed_only = await sh.list_(status_="closed", _r=_CASHIER, _tenant_id=t1, session=session)
    assert len(every) == 1 and len(by_store) == 1 and len(open_only) == 1
    assert closed_only == []


@pytest.mark.integration
async def test_shifts_tenant_isolated(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1, c1 = await _seed_tenant(async_session_factory, subject="kc-sh-i1", email="i1@t.az")
    t2, _c2 = await _seed_tenant(async_session_factory, subject="kc-sh-i2", email="i2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        store_id = await _store(session, t1)
        shift = await sh.open_(_open(store_id, c1), _w=_CASHIER, tenant_id=t1, session=session)
    shift_id = shift.id

    async with _scoped(async_session_factory, t2) as session:
        listed = await sh.list_(_r=_CASHIER, _tenant_id=t2, session=session)
        with pytest.raises(NotFoundError):
            await sh.detail(shift_id, _r=_CASHIER, _tenant_id=t2, session=session)
    assert listed == []


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
def test_shift_write_forbidden_for_clerk(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-sh-clerk", ["clerk"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.post(
            "/v1/shifts",
            json={"store_id": str(uuid4()), "cashier_id": str(uuid4()), "opening_cash_minor": 0},
        )
    assert response.status_code == 403  # clerk has no shift:write


@pytest.mark.integration
def test_shifts_require_tenant_for_super_admin(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> None:
    app = _gated_app("kc-sh-super", ["super_admin"], pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:  # type: ignore[arg-type]
        response = client.get("/v1/shifts")
    assert response.status_code == 403  # passes permission gate, no tenant
