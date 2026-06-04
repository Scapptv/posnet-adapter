"""Channel reconciliation (AI-2.5.6.2, roadmap §17.4).

Drift is inevitable: a push can be swallowed (the dispatcher logs + drops
Auth/Permanent errors), a channel-side edit can diverge from POS, an event can
be lost before it reaches the change feed. Reconciliation is the safety net —
it reads the channel's current state (``fetch_listing``) and compares it to POS
truth (``build_canonical_product``), then repairs any drift with a fresh
``push_stock`` / ``push_price``.

Read-only against POS (it never writes the DB); the only side effects are the
repair pushes to the channel. Channel calls go through the shared
:class:`~services.core.app.sync.guard.ChannelGuard` (rate limit + breaker), but
the error policy is *batch*: any failure on one listing is logged and skipped so
the rest of the run continues (unlike the dispatcher, which re-raises retryable
errors for consumer backoff).

Runs per tenant under that tenant's RLS scope (the listing query and
``build_canonical_product`` are RLS-scoped), driven by
``scripts/reconcile_channel_stock.py`` (``make reconcile``).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.adapter import (
    AdapterError,
    AdapterNotFoundError,
    ChannelAdapter,
    ChannelListingSnapshot,
    CircuitBreakerOpenError,
)
from libs.canonical_model import CanonicalPrice, CanonicalProduct

from ..infrastructure.db.models import Channel, ChannelListing, Variant
from .canonical import build_canonical_product
from .guard import ChannelGuard

_log = logging.getLogger(__name__)

AdapterFactory = Callable[[Channel], Awaitable[ChannelAdapter]]
"""Resolve a channel record to a configured adapter instance (same contract the
dispatcher uses, AI-2.5.2)."""


@dataclass(frozen=True, slots=True)
class ListingReconcileResult:
    """Outcome of reconciling one (channel, variant) listing."""

    sku: str
    channel_code: str
    pos_stock: int | None
    """POS available stock, or ``None`` when the listing was skipped before the
    POS read produced a figure (unpublished product)."""
    channel_stock: int | None
    """Channel-side stock read back, or ``None`` when not listed / fetch failed."""
    stock_drift: bool
    price_drift: bool
    repaired: bool
    note: str | None = None
    """Why a listing was skipped (unpublished / not listed / fetch failed)."""


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Aggregate of one reconcile run."""

    checked: int
    drifted: int
    repaired: int
    results: tuple[ListingReconcileResult, ...]


def _skip(
    sku: str,
    channel_code: str,
    *,
    note: str,
    pos_stock: int | None = None,
    channel_stock: int | None = None,
) -> ListingReconcileResult:
    return ListingReconcileResult(
        sku=sku,
        channel_code=channel_code,
        pos_stock=pos_stock,
        channel_stock=channel_stock,
        stock_drift=False,
        price_drift=False,
        repaired=False,
        note=note,
    )


async def reconcile_channel(
    session: AsyncSession,
    *,
    channel: Channel,
    adapter: ChannelAdapter,
    guard: ChannelGuard,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[ListingReconcileResult]:
    """Reconcile every active, already-pushed listing of ``channel`` vs POS."""
    variants: Sequence[Variant] = (
        (
            await session.execute(
                select(Variant)
                .join(ChannelListing, ChannelListing.variant_id == Variant.id)
                .where(
                    ChannelListing.channel_id == channel.id,
                    ChannelListing.status == "active",
                    ChannelListing.external_listing_id.is_not(None),
                )
                .order_by(Variant.sku)
            )
        )
        .scalars()
        .all()
    )
    results: list[ListingReconcileResult] = []
    for variant in variants:
        results.append(await _reconcile_one(session, channel, adapter, guard, variant, clock))
    return results


async def _reconcile_one(
    session: AsyncSession,
    channel: Channel,
    adapter: ChannelAdapter,
    guard: ChannelGuard,
    variant: Variant,
    clock: Callable[[], datetime],
) -> ListingReconcileResult:
    sku = variant.sku
    canonical = await build_canonical_product(session, variant_id=variant.id, at=clock())
    if canonical is None:
        # Listing exists but the product was unpublished after it was pushed —
        # not this job's concern (a future un-publish flow would delist it).
        return _skip(sku, channel.code, note="not online-published")

    try:
        snapshot: ChannelListingSnapshot | None = await guard.call(
            channel.id, adapter.fetch_listing, sku=sku
        )
    except (AdapterError, CircuitBreakerOpenError) as exc:
        _log.warning(
            "reconcile_fetch_failed",
            extra={"channel_code": channel.code, "sku": sku, "error_type": type(exc).__name__},
        )
        return _skip(
            sku,
            channel.code,
            pos_stock=canonical.stock_qty,
            note=f"fetch failed: {type(exc).__name__}",
        )

    if snapshot is None:
        # POS thinks it's listed (external_listing_id set) but the channel
        # doesn't have it — a re-list is out of scope; surface it for the operator.
        return _skip(sku, channel.code, pos_stock=canonical.stock_qty, note="not listed on channel")

    stock_drift = snapshot.stock != canonical.stock_qty
    price_drift = (
        snapshot.price_minor != canonical.price_minor or snapshot.currency != canonical.currency
    )
    repaired = False
    if stock_drift or price_drift:
        repaired = await _repair(channel, adapter, guard, canonical, stock_drift, price_drift)

    return ListingReconcileResult(
        sku=sku,
        channel_code=channel.code,
        pos_stock=canonical.stock_qty,
        channel_stock=snapshot.stock,
        stock_drift=stock_drift,
        price_drift=price_drift,
        repaired=repaired,
    )


async def _repair(
    channel: Channel,
    adapter: ChannelAdapter,
    guard: ChannelGuard,
    canonical: CanonicalProduct,
    stock_drift: bool,
    price_drift: bool,
) -> bool:
    """Push POS truth back to the channel. Returns whether any repair landed.

    A repair push that fails is logged and counted as not-repaired — the next
    run retries (reconciliation is idempotent: it re-reads then re-pushes)."""
    repaired = False
    if stock_drift:
        try:
            await guard.call(
                channel.id, adapter.push_stock, sku=canonical.sku, qty=canonical.stock_qty
            )
            repaired = True
        except (AdapterError, CircuitBreakerOpenError) as exc:
            _log.warning(
                "reconcile_repair_stock_failed",
                extra={
                    "channel_code": channel.code,
                    "sku": canonical.sku,
                    "error_type": type(exc).__name__,
                },
            )
    if price_drift:
        try:
            await guard.call(
                channel.id,
                adapter.push_price,
                sku=canonical.sku,
                price=CanonicalPrice(
                    sku=canonical.sku,
                    price_minor=canonical.price_minor,
                    currency=canonical.currency,
                ),
            )
            repaired = True
        except (AdapterError, CircuitBreakerOpenError) as exc:
            _log.warning(
                "reconcile_repair_price_failed",
                extra={
                    "channel_code": channel.code,
                    "sku": canonical.sku,
                    "error_type": type(exc).__name__,
                },
            )
    return repaired


async def reconcile_tenant(
    session: AsyncSession,
    *,
    adapter_factory: AdapterFactory,
    guard: ChannelGuard | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ReconcileReport:
    """Reconcile every active channel in the session's (RLS-scoped) tenant."""
    guard = guard or ChannelGuard()
    channels: Sequence[Channel] = (
        (await session.execute(select(Channel).where(Channel.status == "active"))).scalars().all()
    )
    results: list[ListingReconcileResult] = []
    for channel in channels:
        try:
            adapter = await adapter_factory(channel)
        except AdapterNotFoundError:
            # No adapter registered for this channel's code yet — skip it (a real
            # adapter self-registers on import; until then the channel is inert).
            _log.warning("reconcile_no_adapter", extra={"channel_code": channel.code})
            continue
        results.extend(
            await reconcile_channel(
                session, channel=channel, adapter=adapter, guard=guard, clock=clock
            )
        )
    drifted = sum(1 for r in results if r.stock_drift or r.price_drift)
    repaired = sum(1 for r in results if r.repaired)
    return ReconcileReport(
        checked=len(results), drifted=drifted, repaired=repaired, results=tuple(results)
    )
