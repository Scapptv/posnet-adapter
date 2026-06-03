"""AI-2.H2 — data identity & invariants (audit A2/A3/A4, ADR-0016).

Migration 0010 turns four soft guarantees into hard DB invariants:

* ``UNIQUE(tenant_id, sku)`` and partial ``UNIQUE(tenant_id, barcode)`` on
  ``variants`` — POS scans and adapter pushes resolve to exactly one variant.
* ``CHECK (qty >= 0 AND reserved_qty >= 0 AND reserved_qty <= qty)`` on
  ``inventory`` — DB backstop for anti-oversell.
* Journal lock-down: ``stock_movements`` / ``cash_movements`` / ``audit_logs``
  are append-only (``posnet_app`` keeps ``SELECT, INSERT`` only).

The first-create race on inventory now surfaces as ``ConflictError`` (HTTP 409)
instead of a 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.common import ConflictError
from services.core.app.domain.catalog import (
    add_variant,
    create_product,
    find_variant_by_barcode,
    find_variant_by_sku,
)
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.infrastructure.db.models import Inventory
from services.core.app.infrastructure.db.tenant import apply_tenant_scope

APP_ROLE = "posnet_app"
APP_PASSWORD = "posnet_app_dev_pw"  # pragma: allowlist secret  (migration 0009 dev default)


def _app_role_dsn(superuser_dsn: str) -> str:
    parts = urlsplit(superuser_dsn)
    netloc = f"{APP_ROLE}:{APP_PASSWORD}@{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


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


# ----------------------------------------------------------------------------
# A2 — tenant-scoped SKU/barcode uniqueness (deterministic POS lookup)
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_same_sku_across_products_in_tenant_conflicts(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A POS scan by SKU must resolve to one variant — so the same SKU can't
    appear on two products within a tenant. The old per-product constraint did
    not catch this; the new ``UNIQUE(tenant_id, sku)`` does."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-sku-x", email="sku-x@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p1 = await create_product(session, tenant_id=t1, name="P1", currency="AZN")
        p2 = await create_product(session, tenant_id=t1, name="P2", currency="AZN")
        await add_variant(session, tenant_id=t1, product_id=p1.id, sku="DUP", base_price_minor=100)

    p2_id = p2.id
    with pytest.raises(ConflictError):
        async with _scoped(async_session_factory, t1) as session:
            await add_variant(
                session, tenant_id=t1, product_id=p2_id, sku="DUP", base_price_minor=200
            )


@pytest.mark.integration
async def test_same_sku_across_tenants_is_allowed(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two tenants may share the same SKU — uniqueness is scoped to ``tenant_id``."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-sku-t1", email="sku-t1@t.az")
    t2 = await _seed_tenant(async_session_factory, subject="h2-sku-t2", email="sku-t2@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p1 = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v1 = await add_variant(
            session, tenant_id=t1, product_id=p1.id, sku="SHARED", base_price_minor=100
        )
    async with _scoped(async_session_factory, t2) as session:
        p2 = await create_product(session, tenant_id=t2, name="P", currency="AZN")
        v2 = await add_variant(
            session, tenant_id=t2, product_id=p2.id, sku="SHARED", base_price_minor=200
        )
    assert v1.id != v2.id


@pytest.mark.integration
async def test_same_barcode_within_tenant_conflicts(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="h2-bc-x", email="bc-x@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p1 = await create_product(session, tenant_id=t1, name="P1", currency="AZN")
        p2 = await create_product(session, tenant_id=t1, name="P2", currency="AZN")
        await add_variant(
            session,
            tenant_id=t1,
            product_id=p1.id,
            sku="A1",
            barcode="8690000000007",
            base_price_minor=100,
        )

    p2_id = p2.id
    with pytest.raises(ConflictError):
        async with _scoped(async_session_factory, t1) as session:
            await add_variant(
                session,
                tenant_id=t1,
                product_id=p2_id,
                sku="A2",
                barcode="8690000000007",
                base_price_minor=200,
            )


@pytest.mark.integration
async def test_null_barcodes_coexist(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The partial UNIQUE only covers non-NULL barcodes — variants without a
    barcode (legacy / not-yet-labelled stock) must coexist."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-bc-n", email="bc-n@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        a = await add_variant(session, tenant_id=t1, product_id=p.id, sku="A", base_price_minor=1)
        b = await add_variant(session, tenant_id=t1, product_id=p.id, sku="B", base_price_minor=2)
    assert a.barcode is None and b.barcode is None
    assert a.id != b.id


@pytest.mark.integration
async def test_pos_lookup_is_deterministic(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A successful lookup always returns the single variant the constraint
    permits — the ``ORDER BY id`` backstop guarantees it stays deterministic
    even if the constraint were ever relaxed."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-look", email="look@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(
            session,
            tenant_id=t1,
            product_id=p.id,
            sku="POS-1",
            barcode="8690000099999",
            base_price_minor=300,
        )
        by_sku_a = await find_variant_by_sku(session, "POS-1")
        by_sku_b = await find_variant_by_sku(session, "POS-1")
        by_bc_a = await find_variant_by_barcode(session, "8690000099999")
        by_bc_b = await find_variant_by_barcode(session, "8690000099999")
    assert by_sku_a is not None and by_sku_a.id == v.id == by_sku_b.id
    assert by_bc_a is not None and by_bc_a.id == v.id == by_bc_b.id


# ----------------------------------------------------------------------------
# A4 — inventory DB-level CHECK constraints (anti-oversell backstop)
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_inventory_check_qty_nonneg_at_db_level(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Bypassing the domain guard and pushing a negative qty straight into the
    table must be rejected by the CHECK constraint."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-ck-q", email="ck-q@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(session, tenant_id=t1, product_id=p.id, sku="S", base_price_minor=1)
        wh = await create_warehouse(session, tenant_id=t1, name="W", type_="store")
        session.add(
            Inventory(
                tenant_id=t1, variant_id=v.id, warehouse_id=wh.id, qty=-1, reserved_qty=0, version=0
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.integration
async def test_inventory_check_reserved_le_qty_at_db_level(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """``reserved_qty <= qty`` — the row representing "5 reserved out of 3 on
    hand" is forbidden, so anti-oversell holds even if the domain layer is
    skipped."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-ck-r", email="ck-r@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(session, tenant_id=t1, product_id=p.id, sku="S", base_price_minor=1)
        wh = await create_warehouse(session, tenant_id=t1, name="W", type_="store")
        session.add(
            Inventory(
                tenant_id=t1, variant_id=v.id, warehouse_id=wh.id, qty=3, reserved_qty=5, version=0
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.integration
async def test_inventory_check_reserved_nonneg_at_db_level(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t1 = await _seed_tenant(async_session_factory, subject="h2-ck-n", email="ck-n@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(session, tenant_id=t1, product_id=p.id, sku="S", base_price_minor=1)
        wh = await create_warehouse(session, tenant_id=t1, name="W", type_="store")
        session.add(
            Inventory(
                tenant_id=t1, variant_id=v.id, warehouse_id=wh.id, qty=0, reserved_qty=-1, version=0
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


# ----------------------------------------------------------------------------
# A3 — inventory first-create race surfaces as ConflictError (HTTP 409)
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_inventory_unique_variant_warehouse_at_db_level(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The ``UNIQUE(variant_id, warehouse_id)`` is what makes the first-create
    race detectable: a second INSERT for the same pair trips IntegrityError,
    which the domain layer then surfaces as ``ConflictError`` (HTTP 409)."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-uq", email="uq@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(session, tenant_id=t1, product_id=p.id, sku="S", base_price_minor=1)
        wh = await create_warehouse(session, tenant_id=t1, name="W", type_="store")
        variant_id, warehouse_id = v.id, wh.id
        session.add(
            Inventory(
                tenant_id=t1,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                qty=0,
                reserved_qty=0,
                version=0,
            )
        )
        await session.flush()

    with pytest.raises(IntegrityError):
        async with _scoped(async_session_factory, t1) as session:
            session.add(
                Inventory(
                    tenant_id=t1,
                    variant_id=variant_id,
                    warehouse_id=warehouse_id,
                    qty=0,
                    reserved_qty=0,
                    version=0,
                )
            )
            await session.flush()


@pytest.mark.integration
async def test_inventory_apply_movement_first_create_happy_path(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """No race — the first ``in`` movement creates the row and succeeds. Sanity
    check that the new IntegrityError wrap didn't break the normal path."""
    t1 = await _seed_tenant(async_session_factory, subject="h2-fc", email="fc@t.az")
    async with _scoped(async_session_factory, t1) as session:
        p = await create_product(session, tenant_id=t1, name="P", currency="AZN")
        v = await add_variant(session, tenant_id=t1, product_id=p.id, sku="S", base_price_minor=1)
        wh = await create_warehouse(session, tenant_id=t1, name="W", type_="store")
        level = await apply_movement(
            session,
            tenant_id=t1,
            variant_id=v.id,
            warehouse_id=wh.id,
            kind="in",
            qty=5,
        )
    assert level.qty == 5 and level.reserved_qty == 0 and level.version == 1


# ----------------------------------------------------------------------------
# Journal lock-down — append-only stock_movements / cash_movements / audit_logs
# ----------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("table", ["stock_movements", "cash_movements", "audit_logs"])
def test_journal_tables_revoke_update_delete(migrated_db: None, pg_dsn: str, table: str) -> None:
    """``posnet_app`` keeps SELECT + INSERT on every journal but UPDATE/DELETE
    are revoked — a compromised app session cannot rewrite history."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = %s AND table_name = %s",
            (APP_ROLE, table),
        )
        grants = {row[0] for row in cur.fetchall()}
    assert "SELECT" in grants
    assert "INSERT" in grants
    assert "UPDATE" not in grants
    assert "DELETE" not in grants


@pytest.mark.integration
@pytest.mark.parametrize("table", ["stock_movements", "cash_movements", "audit_logs"])
def test_app_role_cannot_update_or_delete_journal(
    migrated_db: None, pg_dsn: str, table: str
) -> None:
    """Live check: the locked-down role gets a permission error trying to
    rewrite a journal row, even with a tenant scope set."""
    fake_tenant = str(uuid4())
    with psycopg.connect(_app_role_dsn(pg_dsn), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (fake_tenant,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(f"UPDATE {table} SET tenant_id = tenant_id")
    with psycopg.connect(_app_role_dsn(pg_dsn), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (fake_tenant,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(f"DELETE FROM {table}")


@pytest.mark.integration
@pytest.mark.parametrize("table", ["stock_movements", "cash_movements", "audit_logs"])
def test_app_role_can_still_insert_journal(migrated_db: None, pg_dsn: str, table: str) -> None:
    """Append-only — but INSERT must still work, otherwise the domain layer
    can no longer write movements/audit entries."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT has_table_privilege(%s, %s, 'INSERT')",
            (APP_ROLE, table),
        )
        row = cur.fetchone()
    assert row is not None and row[0] is True
