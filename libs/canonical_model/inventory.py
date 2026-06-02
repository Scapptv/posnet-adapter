"""Canonical inventory — a targeted stock level for push_stock (AI-1.4)."""

from __future__ import annotations

from .base import CanonicalBase


class CanonicalInventory(CanonicalBase):
    sku: str
    qty: int
    reserved: int = 0

    @property
    def available(self) -> int:
        """Sellable quantity — the anti-oversell figure pushed to channels."""
        return self.qty - self.reserved
