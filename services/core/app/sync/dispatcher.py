"""Sync dispatcher (AI-2.5.2, roadmap §17.3 outbound).

The :class:`SyncDispatcher` is the :class:`~libs.eventbus.EventHandler` that
turns outbox events into adapter calls. It's the bridge between the canonical
event stream (produced by domain mutations, AI-2.H4) and the
channel-agnostic adapter Protocol (AI-2.5.1).

Per event:

1. Resolve the event type to an operation (``push_listing`` /
   ``push_stock`` / ``push_price``) — unknown types are silently skipped
   (foundation events like ``identity.tenant.onboarded`` are not for sync).
2. Find every active :class:`Channel` in the event's tenant.
3. For each channel: take a token from its bucket, route the call through its
   circuit breaker, then call the adapter.
4. On success, update :class:`ChannelListing` (external id, status,
   last_synced_at). On retryable failure, re-raise so the consumer's backoff
   takes over. On permanent/auth failure, log a warning and swallow — the
   reconciliation cron (AI-2.5.6) will catch up.

The dispatcher itself owns the rate limiters + breakers, keyed by channel id,
so per-channel state persists across event handling (state goes away with
the dispatcher instance, typical lifespan = app process).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    ChannelAdapter,
    CircuitBreakerOpenError,
)
from libs.canonical_model import CanonicalPrice
from libs.eventbus import Event

from ..domain.events import (
    CATALOG_VARIANT_ADDED,
    INVENTORY_MOVEMENT_APPLIED,
    PRICING_OVERRIDE_SET,
)
from ..domain.pricing import resolve_price
from ..infrastructure.db.models import Channel, ChannelListing, Variant
from .canonical import build_canonical_product
from .guard import ChannelGuard, GuardConfig

_log = logging.getLogger(__name__)

# Sentinel returned by ``_guard`` when the call did NOT complete — breaker open
# or a swallowed non-retryable error. Distinct from ``None`` (which push_stock /
# push_price return on *success*), so a caller can tell a real sync from a
# skipped one and avoid stamping ``last_synced_at`` on a push that never landed
# (C2, ADR-0020).
_SKIPPED: Any = object()


AdapterFactory = Callable[[Channel], Awaitable[ChannelAdapter]]
"""Resolve a channel record to a configured adapter instance.

Production wiring: looks up the class via :func:`~libs.adapter.get_adapter`
and instantiates it with the channel's config (credentials from Vault). Tests
supply a stub factory that returns a recording adapter.
"""


@dataclass(frozen=True, slots=True)
class DispatcherConfig:
    """Per-channel rate-limit / circuit-breaker tunables.

    Defaults are conservative — a real channel that needs faster rates passes
    its own config (e.g. derived from ``AdapterCapabilities.rate_limit_rps``).
    """

    rate_per_second: float = 1.0
    rate_burst: int = 1
    rate_acquire_timeout_seconds: float = 30.0
    breaker_fail_max: int = 5
    breaker_reset_seconds: float = 60.0


class SyncDispatcher:
    """Long-lived :class:`EventHandler` — instantiate once per app, reuse for
    every consumed event."""

    def __init__(
        self,
        *,
        adapter_factory: AdapterFactory,
        config: DispatcherConfig | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._factory = adapter_factory
        self._config = config or DispatcherConfig()
        self._clock = clock
        # Shared rate-limit + breaker mechanism (also used by reconcile, 5.6.2).
        self._guard_impl = ChannelGuard(
            GuardConfig(
                rate_per_second=self._config.rate_per_second,
                rate_burst=self._config.rate_burst,
                rate_acquire_timeout_seconds=self._config.rate_acquire_timeout_seconds,
                breaker_fail_max=self._config.breaker_fail_max,
                breaker_reset_seconds=self._config.breaker_reset_seconds,
            )
        )

    async def __call__(self, session: AsyncSession, event: Event) -> None:
        """Entry point invoked by :class:`~libs.eventbus.Consumer`."""
        handler = _DISPATCH.get(event.event_type)
        if handler is None:
            return  # not a sync-relevant event (e.g. identity.tenant.onboarded)
        await handler(self, session, event)

    # ----------------------------------------------------------------
    # Per-event handlers
    # ----------------------------------------------------------------

    async def _on_variant_added(self, session: AsyncSession, event: Event) -> None:
        variant_id = UUID(cast(str, event.payload["variant_id"]))
        canonical = await build_canonical_product(session, variant_id=variant_id, at=self._clock())
        if canonical is None:
            return  # product not online-published — sync engine waits

        for channel in await self._active_channels(session, event.tenant_id):
            listing = await self._ensure_listing(
                session, channel_id=channel.id, variant_id=variant_id, tenant_id=event.tenant_id
            )
            adapter = await self._factory(channel)
            results = await self._guard(channel, adapter.push_listing, [canonical])
            if results is _SKIPPED:
                continue
            result = next(iter(results), None)
            if result is None:
                continue
            listing.external_listing_id = result.external_listing_id
            listing.status = result.status
            listing.last_synced_at = self._clock()

    async def _on_movement_applied(self, session: AsyncSession, event: Event) -> None:
        variant_id = UUID(cast(str, event.payload["variant_id"]))
        new_qty = int(cast(int, event.payload["new_qty"]))
        new_reserved = int(cast(int, event.payload["new_reserved_qty"]))
        available = max(new_qty - new_reserved, 0)

        sku = await self._sku(session, variant_id, event.tenant_id)
        if sku is None:
            return

        for listing, channel in await self._active_listings(session, variant_id, event.tenant_id):
            adapter = await self._factory(channel)
            outcome = await self._guard(channel, adapter.push_stock, sku=sku, qty=available)
            # Only stamp last_synced_at when the push actually landed — a swallowed
            # non-retryable failure must leave the listing visibly stale so
            # reconciliation / monitoring re-syncs it (C2, ADR-0020).
            if outcome is not _SKIPPED:
                listing.last_synced_at = self._clock()

    async def _on_override_set(self, session: AsyncSession, event: Event) -> None:
        variant_id = UUID(cast(str, event.payload["variant_id"]))
        sku = await self._sku(session, variant_id, event.tenant_id)
        if sku is None:
            return

        resolved = await resolve_price(session, variant_id=variant_id, at=self._clock())
        price = CanonicalPrice(
            sku=sku,
            price_minor=resolved.effective_price_minor,
            currency=resolved.currency,
        )

        for listing, channel in await self._active_listings(session, variant_id, event.tenant_id):
            adapter = await self._factory(channel)
            outcome = await self._guard(channel, adapter.push_price, sku=sku, price=price)
            if outcome is not _SKIPPED:  # see _on_movement_applied (C2, ADR-0020)
                listing.last_synced_at = self._clock()

    # ----------------------------------------------------------------
    # Channel lookup helpers
    # ----------------------------------------------------------------

    async def _active_channels(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Channel]:
        # Filter by tenant_id EXPLICITLY (C1, ADR-0020): the production Consumer
        # runs the dispatcher on the RLS-exempt system (superuser) pool, so we
        # must not lean on app.current_tenant — otherwise one tenant's event
        # would fan out to every tenant's channels (cross-tenant push).
        return (
            (
                await session.execute(
                    select(Channel).where(
                        Channel.tenant_id == tenant_id, Channel.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _active_listings(
        self, session: AsyncSession, variant_id: UUID, tenant_id: UUID
    ) -> list[tuple[ChannelListing, Channel]]:
        # Explicit tenant_id filter (C1, ADR-0020) — see _active_channels.
        rows = (
            await session.execute(
                select(ChannelListing, Channel)
                .join(Channel, ChannelListing.channel_id == Channel.id)
                .where(
                    ChannelListing.tenant_id == tenant_id,
                    ChannelListing.variant_id == variant_id,
                    ChannelListing.status == "active",
                    Channel.status == "active",
                )
            )
        ).all()
        # SQLAlchemy Row objects are iterable as (listing, channel) but mypy
        # types them as Row[tuple[...]]; the comprehension narrows.
        return [(listing, channel) for listing, channel in rows]

    async def _sku(self, session: AsyncSession, variant_id: UUID, tenant_id: UUID) -> str | None:
        # Explicit tenant_id filter (C1, ADR-0020) — see _active_channels.
        return (
            await session.execute(
                select(Variant.sku).where(Variant.tenant_id == tenant_id, Variant.id == variant_id)
            )
        ).scalar_one_or_none()

    async def _ensure_listing(
        self, session: AsyncSession, *, channel_id: UUID, variant_id: UUID, tenant_id: UUID
    ) -> ChannelListing:
        listing = (
            await session.execute(
                select(ChannelListing).where(
                    ChannelListing.tenant_id == tenant_id,
                    ChannelListing.channel_id == channel_id,
                    ChannelListing.variant_id == variant_id,
                )
            )
        ).scalar_one_or_none()
        if listing is not None:
            return listing
        listing = ChannelListing(
            tenant_id=tenant_id,
            channel_id=channel_id,
            variant_id=variant_id,
            status="pending",
        )
        session.add(listing)
        await session.flush()
        return listing

    # ----------------------------------------------------------------
    # Error-classification policy over the shared ChannelGuard
    # ----------------------------------------------------------------

    async def _guard(
        self,
        channel: Channel,
        op: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Apply rate limit + breaker + error classification around ``op``.

        Returns ``op``'s value on success, the ``_SKIPPED`` sentinel when the
        call was skipped (breaker open) or the adapter raised a non-retryable
        error. Re-raises retryable errors so the consumer's backoff fires.
        """
        try:
            return await self._guard_impl.call(channel.id, op, *args, **kwargs)
        except CircuitBreakerOpenError:
            _log.warning(
                "sync_skip_breaker_open",
                extra={"channel_id": str(channel.id), "channel_code": channel.code},
            )
            return _SKIPPED
        except AdapterRetryableError:
            raise
        except (AdapterAuthError, AdapterPermanentError) as exc:
            _log.warning(
                "sync_non_retryable_error",
                extra={
                    "channel_id": str(channel.id),
                    "channel_code": channel.code,
                    "error_type": type(exc).__name__,
                    "error_message": exc.message,
                },
            )
            return _SKIPPED


# Module-level dispatch table — declared after the class so the methods are
# bound; runtime lookup is O(1).
_DISPATCH: dict[str, Callable[[SyncDispatcher, AsyncSession, Event], Awaitable[None]]] = {
    CATALOG_VARIANT_ADDED: SyncDispatcher._on_variant_added,
    INVENTORY_MOVEMENT_APPLIED: SyncDispatcher._on_movement_applied,
    PRICING_OVERRIDE_SET: SyncDispatcher._on_override_set,
}
