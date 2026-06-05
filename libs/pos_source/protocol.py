"""The ``PosSourceAdapter`` Protocol (AI-2.8) — the POS side of the hub.

The marketplace/delivery side speaks :class:`~libs.adapter.ChannelAdapter`
(outbound: hub → channel). The POS side is its mirror image: the *source of
truth* is an external POS — **Posnet** — and the hub pulls its catalog/stock in
and writes channel orders back. ``PosSourceAdapter`` is that contract, with the
same shape philosophy as the channel adapter: one class per POS, the canonical
model as the wire format, a mock-first implementation that a real connector
swaps into later (ADR-0021).

The hub does **not** implement a POS — Posnet owns product/stock/price. This
adapter only *connects* to it:

* :meth:`pull_catalog` — read the POS catalog (products + stock + price) as
  canonical products, which ``sync_catalog_from_pos`` projects into the hub's
  online catalog/inventory.
* :meth:`push_order` — write a channel order back into the POS (the tail of the
  inbound flow: channel → webhook → reserve → POS). Optional; adapters whose POS
  is read-only may raise ``NotImplementedError`` (gated by
  ``capabilities.supports_push_order``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from libs.canonical_model import CanonicalOrder, CanonicalProduct


@dataclass(frozen=True, slots=True)
class PosSourceCapabilities:
    """What a POS source can do. Class-level; read before instantiating."""

    code: str
    """Stable identifier for the POS (e.g. ``"posnet"``)."""

    name: str
    """Human-readable name."""

    supports_pull_catalog: bool = True
    """The hub can read the POS catalog (products/stock/price)."""

    supports_push_order: bool = False
    """The hub can write channel orders back into the POS."""


@runtime_checkable
class PosSourceAdapter(Protocol):
    """The one Protocol every POS connector implements (Posnet, and later others)."""

    capabilities: PosSourceCapabilities
    """What the POS can do. Class-level; never mutated at runtime."""

    async def pull_catalog(self) -> Sequence[CanonicalProduct]:
        """Read the POS's catalog as canonical products (sku, name, barcode,
        category, price, stock). The hub projects these into its online
        catalog/inventory via ``sync_catalog_from_pos``."""
        ...

    async def push_order(self, order: CanonicalOrder) -> None:
        """Write a channel order back into the POS so stock/sales stay in sync.

        Only called when ``capabilities.supports_push_order`` is true; read-only
        adapters may raise ``NotImplementedError``."""
        ...
