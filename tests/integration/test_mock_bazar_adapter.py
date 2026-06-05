"""Part V V1.1 — :class:`MockBazarAdapter` passes the same contract suite.

The 2nd adapter against a differently-shaped channel. If the abstract
``AdapterContractTests`` pass here *unchanged*, the thesis holds: a new channel
costs one adapter + this subclass, no engine changes — even when the wire shape
diverges (nested money, list category, PUT verbs, different status vocab). All
ASGI-transport / synthetic — no DB, no Docker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from libs.adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRateLimitError,
    AdapterRetryableError,
    ChannelAdapter,
)
from libs.canonical_model import CanonicalPrice, CanonicalProduct, OrderStatus
from mocks.mock_bazar import MockBazarStore
from mocks.mock_bazar import create_app as create_bazar_app
from mocks.mock_bazar.models import SaleItem
from services.core.app.adapters.mock_bazar import MockBazarAdapter, MockBazarConfig
from tests.contract.adapter_contract import AdapterContractTests

BASE = "http://mock-bazar"


def _client_for_app(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url=BASE)


# ----------------------------------------------------------------
# Contract suite — same class, different channel shape
# ----------------------------------------------------------------


class TestMockBazarContract(AdapterContractTests):
    @pytest.fixture
    async def adapter(self) -> AsyncIterator[ChannelAdapter]:
        mock = create_bazar_app()
        adapter = MockBazarAdapter(MockBazarConfig(base_url=BASE), client=_client_for_app(mock))
        try:
            yield adapter
        finally:
            await adapter.aclose()

    @pytest.fixture
    def a_product(self) -> CanonicalProduct:
        return CanonicalProduct(
            sku="BZR-CONTRACT-1",
            barcode="8690000000010",
            name="Test Product",
            attributes={"color": "blue"},
            category_path=("Drinks", "Tea"),
            price_minor=420,
            currency="AZN",
            stock_qty=15,
        )

    @pytest.fixture
    def a_resolved_price(self) -> CanonicalPrice:
        return CanonicalPrice(sku="BZR-CONTRACT-1", price_minor=399, currency="AZN")


# ----------------------------------------------------------------
# Bazar-specific: the distinct-shape mapping actually round-trips
# ----------------------------------------------------------------


@pytest.fixture
async def adapter_with_store() -> AsyncIterator[tuple[MockBazarAdapter, MockBazarStore]]:
    store = MockBazarStore()
    mock = create_bazar_app(store)
    adapter = MockBazarAdapter(MockBazarConfig(base_url=BASE), client=_client_for_app(mock))
    try:
        yield adapter, store
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_push_listing_maps_nested_price_and_list_category(
    adapter_with_store: tuple[MockBazarAdapter, MockBazarStore],
) -> None:
    """Canonical -> Bazar: flat price_minor/currency becomes a nested ``price``
    object, ``category_path`` stays a list, ``live`` maps to ``active``."""
    adapter, store = adapter_with_store
    product = CanonicalProduct(
        sku="SKU-B1",
        barcode="8690000000011",
        name="Cola",
        category_path=("Drinks", "Soda"),
        price_minor=250,
        currency="AZN",
        stock_qty=12,
    )
    [result] = await adapter.push_listing([product])

    assert result.sku == "SKU-B1"
    assert result.external_listing_id.startswith("BZR-")
    assert result.status == "active"  # Bazar "live" -> canonical "active"
    stored = store.product_by_sku("SKU-B1")
    assert stored is not None
    assert stored.amount_minor == 250 and stored.category_path == ["Drinks", "Soda"]


@pytest.mark.integration
async def test_pull_orders_maps_bazar_sale_to_canonical(
    adapter_with_store: tuple[MockBazarAdapter, MockBazarStore],
) -> None:
    """Bazar -> canonical: nested ``items``/``totals``/``buyer`` and the ``new``
    state normalise into a ``CanonicalOrder``."""
    adapter, store = adapter_with_store
    store.seed_sale(
        items=[SaleItem(merchant_sku="X", units=2, unit_amount_minor=150, label="Item X")],
        currency="AZN",
        buyer_name="Aysel",
    )
    from datetime import UTC, datetime

    orders = await adapter.pull_orders(since=datetime(2026, 1, 1, tzinfo=UTC))

    assert len(orders) == 1
    order = orders[0]
    assert order.channel_order_id.startswith("BZR-SALE-")
    assert order.lines[0].sku == "X" and order.lines[0].qty == 2
    assert order.totals.grand_total_minor == 300
    assert order.customer is not None and order.customer.name == "Aysel"
    assert order.status is OrderStatus.PENDING  # Bazar "new" -> "pending"


@pytest.mark.integration
async def test_acknowledge_maps_status_vocab(
    adapter_with_store: tuple[MockBazarAdapter, MockBazarStore],
) -> None:
    """Hub acks in canonical vocab ("confirmed"); Bazar records its own ("accepted")."""
    adapter, store = adapter_with_store
    sale = store.seed_sale(
        items=[SaleItem(merchant_sku="Y", units=1, unit_amount_minor=100, label="Y")],
        currency="AZN",
        buyer_name=None,
    )
    await adapter.acknowledge_order(channel_order_id=sale.ref, status="confirmed")
    assert store.last_state(sale.ref) == "accepted"


# ----------------------------------------------------------------
# Error classification (shared internals) — one synthetic check
# ----------------------------------------------------------------


class _FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None) -> None:
        self._status = status_code
        self._headers = headers or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status, content=b"boom", headers=self._headers)


def _adapter_with_transport(transport: httpx.AsyncBaseTransport) -> MockBazarAdapter:
    return MockBazarAdapter(
        MockBazarConfig(base_url=BASE),
        client=httpx.AsyncClient(transport=transport, base_url=BASE),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (503, AdapterRetryableError),
        (429, AdapterRateLimitError),
        (401, AdapterAuthError),
        (400, AdapterPermanentError),
    ],
)
async def test_error_classification(status_code: int, expected: type[Exception]) -> None:
    adapter = _adapter_with_transport(_FakeTransport(status_code))
    try:
        with pytest.raises(expected):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()
