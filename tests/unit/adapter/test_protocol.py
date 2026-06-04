"""Unit tests for the ChannelAdapter Protocol (AI-2.5.1).

The Protocol is runtime-checkable; isinstance() against a fully-implemented
class is the contract surface the sync engine relies on. These tests pin the
shape: a class that omits any method should NOT satisfy isinstance.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar

import pytest

from libs.adapter import AdapterCapabilities, ChannelAdapter, ChannelListingResult
from libs.canonical_model import CanonicalOrder, CanonicalPrice, CanonicalProduct


def _caps(code: str = "x") -> AdapterCapabilities:
    return AdapterCapabilities(code=code, name="X", auth_kind="none")


class _Complete:
    capabilities: ClassVar[AdapterCapabilities] = _caps()

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


class _MissingPushStock:
    capabilities: ClassVar[AdapterCapabilities] = _caps()

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        return []

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        return None

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        return []

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        return None

    def map_category(self, canonical_category: Sequence[str]) -> str:
        return "/".join(canonical_category)


@pytest.mark.unit
def test_complete_adapter_satisfies_protocol() -> None:
    assert isinstance(_Complete(), ChannelAdapter)


@pytest.mark.unit
def test_missing_method_fails_protocol_check() -> None:
    """A class that drops a method (e.g. forgot ``push_stock``) must NOT pass
    runtime isinstance — the sync engine catches the gap at registration time."""
    assert not isinstance(_MissingPushStock(), ChannelAdapter)


@pytest.mark.unit
def test_channel_listing_result_carries_status_default() -> None:
    result = ChannelListingResult(sku="X-1", external_listing_id="TR-99")
    assert result.sku == "X-1"
    assert result.external_listing_id == "TR-99"
    assert result.status == "active"


@pytest.mark.unit
def test_channel_listing_result_is_frozen() -> None:
    result = ChannelListingResult(sku="X-1", external_listing_id="TR-99")
    with pytest.raises((AttributeError, Exception)):
        result.sku = "X-2"  # type: ignore[misc]
