"""Tenant-scoped pricing (AI-2.3).

The effective sell price of a variant is its catalog ``base_price_minor`` unless an
active :class:`PriceOverride` applies. Resolution precedence: a store-specific
override beats a tenant-wide one, and among equals the most recently created wins;
only overrides whose validity window contains the evaluation time count.

The currency comes from the variant's product (catalog), so a price is always a
complete ``Money`` (minor + currency). The richer rule engine (percent/tiered) is
deferred (roadmap §16); this is the simple base + optional-override layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import NotFoundError, ValidationError
from libs.eventbus import Event, enqueue

from ..infrastructure.db.models import PriceOverride, Product, Store, Variant
from .events import PRICING_OVERRIDE_SET


@dataclass(frozen=True)
class ResolvedPrice:
    variant_id: UUID
    currency: str
    base_price_minor: int
    effective_price_minor: int
    source: str  # "base" | "override"
    override_id: UUID | None


async def set_override(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    variant_id: UUID,
    price_minor: int,
    store_id: UUID | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> PriceOverride:
    if (await session.execute(select(Variant.id).where(Variant.id == variant_id))).first() is None:
        raise NotFoundError("variant not found in this tenant")
    if store_id is not None:
        store = (await session.execute(select(Store.id).where(Store.id == store_id))).first()
        if store is None:
            raise NotFoundError("store not found in this tenant")
    # M7 (ADR-0020): a window that ends at or before it starts can never be active
    # — reject it at write time instead of silently storing a dead override.
    if valid_from is not None and valid_to is not None and valid_from >= valid_to:
        raise ValidationError("valid_from must be before valid_to")

    override = PriceOverride(
        tenant_id=tenant_id,
        variant_id=variant_id,
        store_id=store_id,
        price_minor=price_minor,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(override)
    await session.flush()
    await session.refresh(override)
    await enqueue(
        session,
        Event(
            event_type=PRICING_OVERRIDE_SET,
            tenant_id=tenant_id,
            payload={
                "override_id": str(override.id),
                "variant_id": str(variant_id),
                "store_id": str(store_id) if store_id is not None else None,
                "price_minor": price_minor,
                "valid_from": valid_from.isoformat() if valid_from is not None else None,
                "valid_to": valid_to.isoformat() if valid_to is not None else None,
            },
        ),
    )
    return override


async def resolve_price(
    session: AsyncSession, *, variant_id: UUID, at: datetime, store_id: UUID | None = None
) -> ResolvedPrice:
    """The effective price for ``variant_id`` at time ``at`` (optionally for ``store_id``)."""
    row = (
        await session.execute(
            select(Variant.base_price_minor, Product.currency)
            .join(Product, Variant.product_id == Product.id)
            .where(Variant.id == variant_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("variant not found in this tenant")
    base_price_minor, currency = row

    # Validity is the half-open interval [valid_from, valid_to): from inclusive,
    # to exclusive (H3, ADR-0020); NULL means open-ended on that side.
    conditions = [
        PriceOverride.variant_id == variant_id,
        or_(PriceOverride.valid_from.is_(None), PriceOverride.valid_from <= at),
        or_(PriceOverride.valid_to.is_(None), PriceOverride.valid_to > at),
    ]
    if store_id is not None:
        conditions.append(or_(PriceOverride.store_id == store_id, PriceOverride.store_id.is_(None)))
    else:
        conditions.append(PriceOverride.store_id.is_(None))

    override = (
        await session.execute(
            select(PriceOverride)
            .where(*conditions)
            # store-specific beats tenant-wide; newest wins; PriceOverride.id is the
            # deterministic final tiebreak (H5, ADR-0020) — created_at is
            # transaction-time, so overrides written in one tx tie on it and would
            # otherwise resolve arbitrarily (non-deterministic pushed price).
            .order_by(
                PriceOverride.store_id.is_not(None).desc(),
                PriceOverride.created_at.desc(),
                PriceOverride.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if override is None:
        return ResolvedPrice(variant_id, currency, base_price_minor, base_price_minor, "base", None)
    return ResolvedPrice(
        variant_id, currency, base_price_minor, override.price_minor, "override", override.id
    )
