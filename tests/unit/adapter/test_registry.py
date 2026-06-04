"""Unit tests for the adapter registry (AI-2.5.1)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import ClassVar

import pytest

from libs.adapter import (
    AdapterAlreadyRegisteredError,
    AdapterCapabilities,
    AdapterNotFoundError,
    ChannelListingResult,
    ChannelListingSnapshot,
    clear_registry,
    get_adapter,
    list_adapters,
    register_adapter,
)
from libs.canonical_model import CanonicalOrder, CanonicalPrice, CanonicalProduct


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    clear_registry()
    yield
    clear_registry()


def _make_adapter(code: str, name: str = "X") -> type:
    """Build a minimal class that satisfies the ChannelAdapter Protocol."""
    caps = AdapterCapabilities(code=code, name=name, auth_kind="none")

    class _Adapter:
        capabilities: ClassVar[AdapterCapabilities] = caps

        async def push_listing(
            self, products: Sequence[CanonicalProduct]
        ) -> Sequence[ChannelListingResult]:
            return []

        async def push_stock(self, *, sku: str, qty: int) -> None:
            return None

        async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
            return None

        async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
            return []

        async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
            return None

        def map_category(self, canonical_category: Sequence[str]) -> str:
            return "/".join(canonical_category)

        def normalize_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> CanonicalOrder:
            raise NotImplementedError

        async def fetch_listing(self, *, sku: str) -> ChannelListingSnapshot | None:
            return None

    _Adapter.__name__ = f"{name}Adapter"
    return _Adapter


@pytest.mark.unit
def test_registry_starts_empty() -> None:
    assert list_adapters() == []


@pytest.mark.unit
def test_register_then_get() -> None:
    adapter = _make_adapter("birmarket", "Birmarket")
    register_adapter("birmarket", adapter)
    assert get_adapter("birmarket") is adapter


@pytest.mark.unit
def test_get_missing_raises() -> None:
    with pytest.raises(AdapterNotFoundError, match="ghost"):
        get_adapter("ghost")


@pytest.mark.unit
def test_double_register_same_class_is_idempotent() -> None:
    """Re-importing the adapter module (typical in tests) shouldn't blow up."""
    adapter = _make_adapter("x")
    register_adapter("x", adapter)
    register_adapter("x", adapter)  # no raise
    assert get_adapter("x") is adapter


@pytest.mark.unit
def test_register_collision_raises() -> None:
    """Two distinct classes under the same code is a configuration mistake —
    caught at startup, not at first dispatch."""
    a, b = _make_adapter("x", "A"), _make_adapter("x", "B")
    register_adapter("x", a)
    with pytest.raises(AdapterAlreadyRegisteredError, match="x"):
        register_adapter("x", b)


@pytest.mark.unit
def test_register_with_mismatched_code_raises() -> None:
    """``code`` arg must match the class's declared ``capabilities.code`` —
    catches copy-paste errors where the registration string drifted from the
    capabilities."""
    adapter = _make_adapter("x")
    with pytest.raises(ValueError, match=r"capabilities\.code"):
        register_adapter("typo", adapter)


@pytest.mark.unit
def test_list_adapters_orders_by_code() -> None:
    register_adapter("c", _make_adapter("c", "C"))
    register_adapter("a", _make_adapter("a", "A"))
    register_adapter("b", _make_adapter("b", "B"))
    codes = [caps.code for caps in list_adapters()]
    assert codes == ["a", "b", "c"]


@pytest.mark.unit
def test_clear_registry_empties_state() -> None:
    register_adapter("x", _make_adapter("x"))
    assert list_adapters() != []
    clear_registry()
    assert list_adapters() == []
