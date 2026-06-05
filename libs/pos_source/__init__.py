"""POS-source connector contract (AI-2.8, ADR-0021).

The hub connects to an external POS (Posnet) as its source of truth — pulls the
catalog/stock in, writes channel orders back. ``PosSourceAdapter`` is the
contract; a real Posnet connector swaps in for the mock once the Posnet
interface is known.
"""

from __future__ import annotations

from .protocol import PosSourceAdapter, PosSourceCapabilities

__all__ = ["PosSourceAdapter", "PosSourceCapabilities"]
