"""AI-1.4 — CanonicalInventory: reserved default + available (anti-oversell)."""

from __future__ import annotations

import pytest

from libs.canonical_model import CanonicalInventory


@pytest.mark.unit
def test_reserved_defaults_to_zero() -> None:
    inv = CanonicalInventory(sku="S", qty=10)
    assert inv.reserved == 0
    assert inv.available == 10


@pytest.mark.unit
def test_available_subtracts_reserved() -> None:
    inv = CanonicalInventory(sku="S", qty=10, reserved=3)
    assert inv.available == 7
