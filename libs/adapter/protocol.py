"""The ``ChannelAdapter`` Protocol (AI-2.5.1, roadmap §17.2).

Every channel adapter implements this Protocol. The sync engine talks only to
this surface — it never imports a specific adapter, never knows a channel's
wire format. Adding a channel means writing one class + a contract test; the
rest of the platform stays the same.

Outbound (POS → channel) — four push operations:

* :meth:`push_listing` — publish a new product (returns the channel's
  external listing id, which the sync engine stores in
  ``channel_listings.external_listing_id``).
* :meth:`push_stock` — push an updated stock level for an existing listing.
* :meth:`push_price` — push an updated price.

Inbound (channel → POS) — two ingest paths (adapter declares which via
``capabilities``):

* :meth:`pull_orders` — poll the channel for new orders since a watermark.
* :meth:`acknowledge_order` — confirm an order was received / its status.

Mapping helpers (sync, no IO):

* :meth:`map_category` — translate the canonical category path into the
  channel's category code/string.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from libs.canonical_model import CanonicalOrder, CanonicalPrice, CanonicalProduct

from .capabilities import AdapterCapabilities


@dataclass(frozen=True, slots=True)
class ChannelListingResult:
    """The outcome of a ``push_listing`` call for one product.

    The sync engine stores ``external_listing_id`` on the matching
    ``channel_listings`` row so subsequent ``push_stock`` / ``push_price`` calls
    can target it.
    """

    sku: str
    """The canonical SKU the push was for (echoes back the input)."""

    external_listing_id: str
    """The channel's identifier for the new listing."""

    status: str = "active"
    """Lifecycle hint: ``"active"`` | ``"pending"`` | ``"rejected"``.
    Mirrors ``channel_listings.status``."""


@dataclass(frozen=True, slots=True)
class ChannelListingSnapshot:
    """The channel's *current* view of a listing — what reconciliation reads to
    compare against POS (AI-2.5.6).

    ``fetch_listing`` returns this so the reconciliation job can detect drift
    (channel ``stock`` != POS available) and repair it with a fresh
    ``push_stock``. ``None`` from ``fetch_listing`` means the SKU isn't listed
    on the channel at all.
    """

    sku: str
    """The canonical SKU this snapshot is for."""

    stock: int
    """The channel's current sellable stock for the listing."""

    price_minor: int
    """The channel's current price, in minor units."""

    currency: str
    """ISO-4217 currency of ``price_minor``."""

    external_listing_id: str
    """The channel's identifier for the listing."""

    status: str = "active"
    """Channel-side lifecycle: ``"active"`` | ``"pending"`` | ``"rejected"``."""


@runtime_checkable
class ChannelAdapter(Protocol):
    """The one Protocol every channel adapter implements.

    ``capabilities`` is class-level (the sync engine reads it before
    instantiating); every other method is async (the engine talks to all
    channels concurrently).
    """

    capabilities: AdapterCapabilities
    """What the channel can do. Class-level; never mutated at runtime."""

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        """Publish each product as a listing on the channel.

        Returns one :class:`ChannelListingResult` per input product, in the
        same order. Raises an :class:`~libs.adapter.AdapterError` subclass on
        any non-success.
        """
        ...

    async def push_stock(self, *, sku: str, qty: int) -> None:
        """Push the latest available stock figure for ``sku``.

        ``qty`` is the canonical ``stock_qty`` (already aggregated across
        online-sellable warehouses by ``build_canonical_product``).
        """
        ...

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        """Push the latest price for ``sku``."""
        ...

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        """Return every order placed on the channel after ``since``.

        Only called when ``capabilities.supports_pull_orders`` is true.
        Pagination (if any) is the adapter's concern; the engine treats the
        return value as the full batch.
        """
        ...

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        """Tell the channel the order was received / its new status.

        Idempotent on ``(channel_order_id, status)`` — the sync engine may
        re-call after a retry.
        """
        ...

    def map_category(self, canonical_category: Sequence[str]) -> str:
        """Translate the canonical category path into the channel's category
        code/string.

        Pure / synchronous: no IO. Adapters typically hold a mapping table
        keyed on the tuple of canonical segments.
        """
        ...

    def normalize_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> CanonicalOrder:
        """Parse a channel order webhook body into a :class:`CanonicalOrder`.

        Pure / synchronous: no IO, no DB. The webhook endpoint has already
        verified the HMAC signature; the adapter only has to reshape the
        channel's JSON into the canonical envelope. Adapters whose channel
        ingests via :meth:`pull_orders` instead may raise ``NotImplementedError``
        — the webhook endpoint checks ``capabilities.supports_webhook_orders``
        before calling.
        """
        ...

    async def fetch_listing(self, *, sku: str) -> ChannelListingSnapshot | None:
        """Read the channel's current state for ``sku`` (stock, price, status).

        Reconciliation (AI-2.5.6) calls this to detect drift between the
        channel and POS, then repairs with a fresh ``push_stock``. Returns
        ``None`` if ``sku`` isn't listed on the channel. Only called when
        ``capabilities.supports_fetch_listing`` is true; push-only adapters
        may raise ``NotImplementedError``.
        """
        ...
