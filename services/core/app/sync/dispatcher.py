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
    CircuitBreaker,
    CircuitBreakerOpenError,
    TokenBucket,
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

_log = logging.getLogger(__name__)


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
        self._limiters: dict[UUID, TokenBucket] = {}
        self._breakers: dict[UUID, CircuitBreaker] = {}

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

        for channel in await self._active_channels(session):
            listing = await self._ensure_listing(
                session, channel_id=channel.id, variant_id=variant_id, tenant_id=event.tenant_id
            )
            adapter = await self._factory(channel)
            results = await self._guard(channel, adapter.push_listing, [canonical])
            if results is None:
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

        sku = await self._sku(session, variant_id)
        if sku is None:
            return

        for listing, channel in await self._active_listings(session, variant_id):
            adapter = await self._factory(channel)
            await self._guard(channel, adapter.push_stock, sku=sku, qty=available)
            listing.last_synced_at = self._clock()

    async def _on_override_set(self, session: AsyncSession, event: Event) -> None:
        variant_id = UUID(cast(str, event.payload["variant_id"]))
        sku = await self._sku(session, variant_id)
        if sku is None:
            return

        resolved = await resolve_price(session, variant_id=variant_id, at=self._clock())
        price = CanonicalPrice(
            sku=sku,
            price_minor=resolved.effective_price_minor,
            currency=resolved.currency,
        )

        for listing, channel in await self._active_listings(session, variant_id):
            adapter = await self._factory(channel)
            await self._guard(channel, adapter.push_price, sku=sku, price=price)
            listing.last_synced_at = self._clock()

    # ----------------------------------------------------------------
    # Channel lookup helpers
    # ----------------------------------------------------------------

    async def _active_channels(self, session: AsyncSession) -> Sequence[Channel]:
        return (
            (await session.execute(select(Channel).where(Channel.status == "active")))
            .scalars()
            .all()
        )

    async def _active_listings(
        self, session: AsyncSession, variant_id: UUID
    ) -> list[tuple[ChannelListing, Channel]]:
        rows = (
            await session.execute(
                select(ChannelListing, Channel)
                .join(Channel, ChannelListing.channel_id == Channel.id)
                .where(
                    ChannelListing.variant_id == variant_id,
                    ChannelListing.status == "active",
                    Channel.status == "active",
                )
            )
        ).all()
        # SQLAlchemy Row objects are iterable as (listing, channel) but mypy
        # types them as Row[tuple[...]]; the comprehension narrows.
        return [(listing, channel) for listing, channel in rows]

    async def _sku(self, session: AsyncSession, variant_id: UUID) -> str | None:
        return (
            await session.execute(select(Variant.sku).where(Variant.id == variant_id))
        ).scalar_one_or_none()

    async def _ensure_listing(
        self, session: AsyncSession, *, channel_id: UUID, variant_id: UUID, tenant_id: UUID
    ) -> ChannelListing:
        listing = (
            await session.execute(
                select(ChannelListing).where(
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
    # Rate limit + circuit breaker + error classification
    # ----------------------------------------------------------------

    def _limiter_for(self, channel_id: UUID) -> TokenBucket:
        limiter = self._limiters.get(channel_id)
        if limiter is None:
            limiter = TokenBucket(
                rate_per_second=self._config.rate_per_second,
                capacity=self._config.rate_burst,
            )
            self._limiters[channel_id] = limiter
        return limiter

    def _breaker_for(self, channel_id: UUID) -> CircuitBreaker:
        breaker = self._breakers.get(channel_id)
        if breaker is None:
            breaker = CircuitBreaker(
                fail_max=self._config.breaker_fail_max,
                reset_timeout=self._config.breaker_reset_seconds,
                # Don't trip the breaker on non-retryable errors — they're
                # caused by bad payloads or stale credentials, not a sick
                # upstream.
                excluded_exceptions=(AdapterAuthError, AdapterPermanentError),
            )
            self._breakers[channel_id] = breaker
        return breaker

    async def _guard(
        self,
        channel: Channel,
        op: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any | None:
        """Apply rate limit + breaker + error classification around ``op``.

        Returns ``op``'s value on success, ``None`` when the call was skipped
        (breaker open) or the adapter raised a non-retryable error. Re-raises
        retryable errors so the consumer's backoff fires.
        """
        await self._limiter_for(channel.id).acquire(
            timeout=self._config.rate_acquire_timeout_seconds
        )
        breaker = self._breaker_for(channel.id)
        try:
            return await breaker.call(op, *args, **kwargs)
        except CircuitBreakerOpenError:
            _log.warning(
                "sync_skip_breaker_open",
                extra={"channel_id": str(channel.id), "channel_code": channel.code},
            )
            return None
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
            return None


# Module-level dispatch table — declared after the class so the methods are
# bound; runtime lookup is O(1).
_DISPATCH: dict[str, Callable[[SyncDispatcher, AsyncSession, Event], Awaitable[None]]] = {
    CATALOG_VARIANT_ADDED: SyncDispatcher._on_variant_added,
    INVENTORY_MOVEMENT_APPLIED: SyncDispatcher._on_movement_applied,
    PRICING_OVERRIDE_SET: SyncDispatcher._on_override_set,
}
