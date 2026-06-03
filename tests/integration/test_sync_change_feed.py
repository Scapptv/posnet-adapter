"""AI-2.H4 — sync change-feed (outbox emit + consume idempotency).

Audit B1 (catalog/inventory/pricing emit zero outbox events) + B5 (consumer
side has no idempotency_keys wiring) are the two things that make the rest of
the integration story impossible — without a change-feed there's nothing for
the sync engine to project, and without dedupe a re-delivered event would
double-post to a channel.

These tests prove:

1. Every mutating domain function commits one outbox row, atomically with the
   business write (rolls back together).
2. The consumer wraps each delivery in :func:`idempotent`, so a redelivered
   ``event_id`` short-circuits before the handler's side effect runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.eventbus import Event
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.events import (
    CATALOG_PRODUCT_CREATED,
    CATALOG_VARIANT_ADDED,
    INVENTORY_MOVEMENT_APPLIED,
    PRICING_OVERRIDE_SET,
)
from services.core.app.domain.inventory import apply_movement, create_warehouse
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.domain.pricing import set_override
from services.core.app.idempotency import idempotent
from services.core.app.infrastructure.db.tenant import apply_tenant_scope


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


async def _outbox_events(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, event_type: str
) -> list[dict[str, object]]:
    async with factory() as session, session.begin():
        # Owner session reads cross-tenant; filter by tenant explicitly.
        result = await session.execute(
            text(
                "SELECT id, tenant_id, event_type, payload, published "
                "FROM outbox_events WHERE tenant_id = :tid AND event_type = :et "
                "ORDER BY created_at"
            ),
            {"tid": tenant_id, "et": event_type},
        )
        return [dict(row._mapping) for row in result.all()]


# ----------------------------------------------------------------------------
# B1 — catalog/inventory/pricing emit outbox events on every mutation.
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_product_emits_catalog_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-p", email="p@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(
            session, tenant_id=tenant_id, name="Coca Cola", currency="AZN"
        )

    rows = await _outbox_events(async_session_factory, tenant_id, CATALOG_PRODUCT_CREATED)
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["product_id"] == str(product.id)
    assert payload["name"] == "Coca Cola"
    assert payload["currency"] == "AZN"
    assert payload["store_id"] is None
    assert rows[0]["published"] is False  # relay flips it on publish


@pytest.mark.integration
async def test_add_variant_emits_catalog_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-v", email="v@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session,
            tenant_id=tenant_id,
            product_id=product.id,
            sku="SKU-1",
            barcode="8690000111111",
            base_price_minor=1500,
        )

    rows = await _outbox_events(async_session_factory, tenant_id, CATALOG_VARIANT_ADDED)
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["variant_id"] == str(variant.id)
    assert payload["product_id"] == str(product.id)
    assert payload["sku"] == "SKU-1"
    assert payload["barcode"] == "8690000111111"
    assert payload["base_price_minor"] == 1500


@pytest.mark.integration
async def test_inventory_movement_emits_event_with_post_state(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The payload carries the post-movement ``new_qty`` / ``new_reserved_qty``
    so downstream channel adapters can project the level without re-querying."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-i", email="i@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S", base_price_minor=1
        )
        warehouse = await create_warehouse(session, tenant_id=tenant_id, name="W", type_="store")
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse.id,
            kind="in",
            qty=10,
        )
        await apply_movement(
            session,
            tenant_id=tenant_id,
            variant_id=variant.id,
            warehouse_id=warehouse.id,
            kind="reserve",
            qty=3,
        )

    rows = await _outbox_events(async_session_factory, tenant_id, INVENTORY_MOVEMENT_APPLIED)
    assert len(rows) == 2

    first_payload = rows[0]["payload"]
    assert isinstance(first_payload, dict)
    assert first_payload["kind"] == "in"
    assert first_payload["qty"] == 10
    assert first_payload["new_qty"] == 10
    assert first_payload["new_reserved_qty"] == 0
    assert first_payload["version"] == 1

    second_payload = rows[1]["payload"]
    assert isinstance(second_payload, dict)
    assert second_payload["kind"] == "reserve"
    assert second_payload["new_qty"] == 10
    assert second_payload["new_reserved_qty"] == 3
    assert second_payload["version"] == 2


@pytest.mark.integration
async def test_pricing_override_emits_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-pr", email="pr@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="S", base_price_minor=1000
        )
        override = await set_override(
            session, tenant_id=tenant_id, variant_id=variant.id, price_minor=750
        )

    rows = await _outbox_events(async_session_factory, tenant_id, PRICING_OVERRIDE_SET)
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["override_id"] == str(override.id)
    assert payload["variant_id"] == str(variant.id)
    assert payload["price_minor"] == 750
    assert payload["store_id"] is None
    assert payload["valid_from"] is None
    assert payload["valid_to"] is None


@pytest.mark.integration
async def test_outbox_event_rolls_back_with_failed_mutation(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The event commits in the SAME transaction as the row — a conflict on
    the second insert undoes both the row AND the first event. (Otherwise a
    sync push could lead a downstream channel by a phantom row.)"""
    from libs.common import ConflictError

    tenant_id = await _seed_tenant(async_session_factory, subject="h4-rb", email="rb@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="X", base_price_minor=1
        )
    product_id = product.id

    with pytest.raises(ConflictError):  # duplicate SKU in tenant -> tx rolls back
        async with _scoped(async_session_factory, tenant_id) as session:
            await add_variant(
                session, tenant_id=tenant_id, product_id=product_id, sku="X", base_price_minor=2
            )

    # Only the first add_variant emitted an event; the failed second did not.
    rows = await _outbox_events(async_session_factory, tenant_id, CATALOG_VARIANT_ADDED)
    assert len(rows) == 1


# ----------------------------------------------------------------------------
# B5 — consume idempotency (event_id dedup via idempotency_keys).
# ----------------------------------------------------------------------------


@pytest.mark.integration
async def test_idempotent_runs_handler_once_per_event_id(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """First delivery runs the handler and inserts the key; a redelivery of
    the same ``event_id`` ON CONFLICT DO NOTHING returns rowcount=0, so the
    handler is skipped."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-id", email="id@t.az")
    event = Event(event_type="t", tenant_id=tenant_id, payload={"x": 1})

    call_count = 0

    async def handler(_session: AsyncSession, _event: Event) -> None:
        nonlocal call_count
        call_count += 1

    wrapped = idempotent(handler)
    async with async_session_factory() as session, session.begin():
        await wrapped(session, event)
    async with async_session_factory() as session, session.begin():
        await wrapped(session, event)  # redelivery
    async with async_session_factory() as session, session.begin():
        await wrapped(session, event)  # redelivery again

    assert call_count == 1

    # Exactly one idempotency_keys row landed for this event.
    async with async_session_factory() as session, session.begin():
        count = (
            await session.execute(
                text("SELECT count(*) FROM idempotency_keys WHERE key = :k"),
                {"k": str(event.event_id)},
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.integration
async def test_idempotent_rolls_back_key_on_handler_failure(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A handler raising inside the consumer transaction must roll back the
    idempotency row too — otherwise the retry would see the key, skip the
    handler, and the side effect would silently never run."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-fa", email="fa@t.az")
    event = Event(event_type="t", tenant_id=tenant_id, payload={})

    async def handler(_session: AsyncSession, _event: Event) -> None:
        raise RuntimeError("boom")

    wrapped = idempotent(handler)
    with pytest.raises(RuntimeError, match="boom"):
        async with async_session_factory() as session, session.begin():
            await wrapped(session, event)

    async with async_session_factory() as session, session.begin():
        count = (
            await session.execute(
                text("SELECT count(*) FROM idempotency_keys WHERE key = :k"),
                {"k": str(event.event_id)},
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.integration
async def test_idempotent_distinct_event_ids_run_handler_each(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Two distinct events with the same payload — each must run."""
    tenant_id = await _seed_tenant(async_session_factory, subject="h4-2", email="2@t.az")
    event_a = Event(event_type="t", tenant_id=tenant_id, payload={"x": 1})
    event_b = Event(event_type="t", tenant_id=tenant_id, payload={"x": 1})

    call_count = 0

    async def handler(_session: AsyncSession, _event: Event) -> None:
        nonlocal call_count
        call_count += 1

    wrapped = idempotent(handler)
    async with async_session_factory() as session, session.begin():
        await wrapped(session, event_a)
    async with async_session_factory() as session, session.begin():
        await wrapped(session, event_b)

    assert call_count == 2
