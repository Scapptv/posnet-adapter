"""Pricing domain — resolve_price tiebreak + set_override validation (ADR-0020).

Covers the audit fixes:
* H5 — ``resolve_price`` must resolve deterministically when two same-scope
  overrides tie on ``created_at`` (transaction-time): the ``PriceOverride.id``
  tiebreak makes the pushed price stable instead of arbitrary.
* M7 — ``set_override`` rejects an inverted/zero-width validity window
  (``valid_from >= valid_to``) instead of silently storing a dead override.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.common import ValidationError
from services.core.app.domain.catalog import add_variant, create_product
from services.core.app.domain.onboarding import onboard_tenant
from services.core.app.domain.pricing import resolve_price, set_override
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


@pytest.mark.integration
async def test_resolve_price_tiebreak_is_deterministic_for_same_scope(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """H5 (ADR-0020): two tenant-wide overrides created in one transaction tie on
    every prior sort key (scope + created_at). The ``id`` tiebreak must make
    resolution deterministic — the same override every call — so the price pushed
    to a channel never flips between equal candidates."""
    tenant_id = await _seed_tenant(async_session_factory, subject="pr-tb", email="pr-tb@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="TB-1", base_price_minor=1000
        )
        variant_id = variant.id
        # Both tenant-wide, no validity window, SAME transaction → identical
        # created_at (transaction_timestamp). Only id breaks the tie.
        o1 = await set_override(
            session, tenant_id=tenant_id, variant_id=variant_id, price_minor=700
        )
        o2 = await set_override(
            session, tenant_id=tenant_id, variant_id=variant_id, price_minor=800
        )
        # id.desc() → the larger UUID wins (PG byte-order == Python UUID int order).
        expected_override_id = max(o1.id, o2.id)

    seen: list[UUID | None] = []
    for _ in range(3):
        async with _scoped(async_session_factory, tenant_id) as session:
            resolved = await resolve_price(session, variant_id=variant_id, at=datetime.now(UTC))
            seen.append(resolved.override_id)

    assert seen[0] == seen[1] == seen[2], f"non-deterministic resolution: {seen}"
    assert seen[0] == expected_override_id


@pytest.mark.integration
async def test_set_override_rejects_inverted_validity_window(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """M7 (ADR-0020): a window whose end is at/before its start can never be
    active — set_override must reject it rather than store a silently-dead row."""
    tenant_id = await _seed_tenant(async_session_factory, subject="pr-vw", email="pr-vw@t.az")
    async with _scoped(async_session_factory, tenant_id) as session:
        product = await create_product(session, tenant_id=tenant_id, name="P", currency="AZN")
        variant = await add_variant(
            session, tenant_id=tenant_id, product_id=product.id, sku="VW-1", base_price_minor=500
        )
        with pytest.raises(ValidationError):
            await set_override(
                session,
                tenant_id=tenant_id,
                variant_id=variant.id,
                price_minor=400,
                valid_from=datetime(2026, 6, 2, tzinfo=UTC),
                valid_to=datetime(2026, 6, 1, tzinfo=UTC),  # before valid_from
            )
        # equal bounds (zero-width) is also rejected
        with pytest.raises(ValidationError):
            await set_override(
                session,
                tenant_id=tenant_id,
                variant_id=variant.id,
                price_minor=400,
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 1, tzinfo=UTC),
            )
