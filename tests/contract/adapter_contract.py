"""Channel-adapter contract test suite (AI-2.5.3, roadmap §17.2).

Every concrete :class:`~libs.adapter.ChannelAdapter` subclasses
:class:`AdapterContractTests` and provides three pytest fixtures —
``adapter``, ``a_product``, ``a_resolved_price`` — pointing at a working
channel. The suite then runs every contract test against it. New adapters
either pass the suite or are not done.

The suite checks contract obligations that aren't visible from the Protocol
alone:

* push_listing returns one result per input, in the same order;
* push_listing is idempotent — re-pushing the same product yields the same
  ``external_listing_id``;
* push_stock + push_price return None on success and raise an
  :class:`~libs.adapter.AdapterError` subclass on failure;
* map_category is pure (same input → same output, no side effects);
* capabilities are stable and meet basic shape requirements.
"""

from __future__ import annotations

import pytest

from libs.adapter import (
    AdapterCapabilities,
    ChannelAdapter,
    ChannelListingResult,
    ChannelListingSnapshot,
)
from libs.canonical_model import CanonicalPrice, CanonicalProduct


@pytest.mark.contract
class AdapterContractTests:
    """Subclass and override the three fixtures below. The class is
    intentionally test-data-agnostic so adapters can keep their own fixtures."""

    @pytest.fixture
    def adapter(self) -> ChannelAdapter:
        raise NotImplementedError(
            "Concrete contract test class must override the `adapter` fixture."
        )

    @pytest.fixture
    def a_product(self) -> CanonicalProduct:
        raise NotImplementedError(
            "Concrete contract test class must override the `a_product` fixture."
        )

    @pytest.fixture
    def a_resolved_price(self) -> CanonicalPrice:
        raise NotImplementedError(
            "Concrete contract test class must override the `a_resolved_price` fixture."
        )

    # ----------------------------------------------------------------
    # Capabilities
    # ----------------------------------------------------------------

    def test_capabilities_present_and_shaped(self, adapter: ChannelAdapter) -> None:
        """Every adapter exposes a non-empty code/name + at least one inbound or
        outbound flow. An adapter that supports neither push nor pull is
        almost always a misconfiguration."""
        caps = adapter.capabilities
        assert isinstance(caps, AdapterCapabilities)
        assert caps.code and caps.name
        any_push = (
            caps.supports_push_listing or caps.supports_push_stock or caps.supports_push_price
        )
        any_ingest = caps.supports_pull_orders or caps.supports_webhook_orders
        assert any_push or any_ingest, "adapter declares neither push nor ingest"

    def test_capabilities_is_class_level(self, adapter: ChannelAdapter) -> None:
        """``capabilities`` lives on the class, not the instance — the sync
        engine reads it without instantiating the adapter."""
        assert type(adapter).capabilities is adapter.capabilities

    # ----------------------------------------------------------------
    # Push contracts
    # ----------------------------------------------------------------

    async def test_push_listing_returns_one_result_per_input(
        self, adapter: ChannelAdapter, a_product: CanonicalProduct
    ) -> None:
        results = await adapter.push_listing([a_product])
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, ChannelListingResult)
        assert result.sku == a_product.sku
        assert result.external_listing_id  # non-empty

    async def test_push_listing_is_idempotent_on_sku(
        self, adapter: ChannelAdapter, a_product: CanonicalProduct
    ) -> None:
        """Re-pushing the same product (same SKU) yields the same external id.
        Otherwise the sync engine would create a new listing on every retry."""
        first = (await adapter.push_listing([a_product]))[0]
        second = (await adapter.push_listing([a_product]))[0]
        assert first.external_listing_id == second.external_listing_id

    async def test_push_stock_returns_none_on_success(
        self, adapter: ChannelAdapter, a_product: CanonicalProduct
    ) -> None:
        """First land a listing so the SKU exists; then a successful update
        returns ``None`` (the adapter signals success by absence of exception)."""
        await adapter.push_listing([a_product])
        result = await adapter.push_stock(sku=a_product.sku, qty=42)
        assert result is None

    async def test_push_price_returns_none_on_success(
        self,
        adapter: ChannelAdapter,
        a_product: CanonicalProduct,
        a_resolved_price: CanonicalPrice,
    ) -> None:
        await adapter.push_listing([a_product])
        result = await adapter.push_price(sku=a_product.sku, price=a_resolved_price)
        assert result is None

    # ----------------------------------------------------------------
    # Fetch (reconciliation read) — only for adapters that support it
    # ----------------------------------------------------------------

    async def test_fetch_listing_reads_back_pushed_stock(
        self, adapter: ChannelAdapter, a_product: CanonicalProduct
    ) -> None:
        """A listing that was just pushed reads back with a matching SKU and the
        stock that was pushed — the input reconciliation compares against POS."""
        if not adapter.capabilities.supports_fetch_listing:
            pytest.skip("adapter does not support fetch_listing")
        await adapter.push_listing([a_product])
        snapshot = await adapter.fetch_listing(sku=a_product.sku)
        assert isinstance(snapshot, ChannelListingSnapshot)
        assert snapshot.sku == a_product.sku
        assert snapshot.stock == a_product.stock_qty
        assert snapshot.external_listing_id  # non-empty

    async def test_fetch_listing_unknown_sku_returns_none(self, adapter: ChannelAdapter) -> None:
        """A SKU the channel never listed reads back as ``None`` (not an error)
        — reconciliation treats it as "not listed here"."""
        if not adapter.capabilities.supports_fetch_listing:
            pytest.skip("adapter does not support fetch_listing")
        assert await adapter.fetch_listing(sku="NO-SUCH-SKU-EVER") is None

    # ----------------------------------------------------------------
    # Mapping
    # ----------------------------------------------------------------

    def test_map_category_is_pure(self, adapter: ChannelAdapter) -> None:
        """No hidden state: same input → same output across calls."""
        path = ("Drinks", "Soft Drinks")
        first = adapter.map_category(path)
        second = adapter.map_category(path)
        assert isinstance(first, str)
        assert first == second

    def test_map_category_handles_empty_path(self, adapter: ChannelAdapter) -> None:
        """A product without categories must still get a stable string back
        (the empty string is a fine choice; raising is not)."""
        assert isinstance(adapter.map_category(()), str)
