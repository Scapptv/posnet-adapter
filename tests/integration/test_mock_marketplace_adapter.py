"""AI-2.5.3 — :class:`MockMarketplaceAdapter` passes the contract suite.

Drives the adapter through the abstract contract test suite + a few
mock-specific checks (pull_orders happy path, error classification on
synthetic responses). Concrete adapters in the future copy this layout: a
contract-suite subclass and a handful of channel-specific tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
from mocks.mock_marketplace import create_app as create_mock_app
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from tests.contract.adapter_contract import AdapterContractTests


def _client_for_app(app: object) -> httpx.AsyncClient:
    """An :mod:`httpx` client wired straight to the FastAPI app's ASGI
    transport — no socket, no port."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://mock-marketplace")


# ----------------------------------------------------------------
# Contract suite — one class subclassing AdapterContractTests
# ----------------------------------------------------------------


class TestMockMarketplaceContract(AdapterContractTests):
    @pytest.fixture
    async def adapter(self) -> AsyncIterator[ChannelAdapter]:
        mock = create_mock_app()
        client = _client_for_app(mock)
        adapter = MockMarketplaceAdapter(
            MockMarketplaceConfig(base_url="http://mock-marketplace"), client=client
        )
        try:
            yield adapter
        finally:
            await adapter.aclose()

    @pytest.fixture
    def a_product(self) -> CanonicalProduct:
        return CanonicalProduct(
            sku="CONTRACT-1",
            barcode="8690000000003",
            name="Test Product",
            attributes={"color": "red"},
            category_path=("Drinks", "Soda"),
            price_minor=300,
            currency="AZN",
            stock_qty=10,
        )

    @pytest.fixture
    def a_resolved_price(self) -> CanonicalPrice:
        return CanonicalPrice(sku="CONTRACT-1", price_minor=275, currency="AZN")


# ----------------------------------------------------------------
# Mock-specific behaviour the contract doesn't cover
# ----------------------------------------------------------------


@pytest.fixture
async def adapter_with_mock() -> AsyncIterator[tuple[MockMarketplaceAdapter, object]]:
    mock = create_mock_app()
    client = _client_for_app(mock)
    adapter = MockMarketplaceAdapter(
        MockMarketplaceConfig(base_url="http://mock-marketplace"), client=client
    )
    try:
        yield adapter, mock
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_pull_orders_returns_canonical_orders(
    adapter_with_mock: tuple[MockMarketplaceAdapter, object],
) -> None:
    """Seed a mock order, pull from a watermark before it, and verify the
    adapter reshapes the channel JSON into ``CanonicalOrder``."""
    adapter, mock = adapter_with_mock
    async with _client_for_app(mock) as direct:
        await direct.post(
            "/_test/orders",
            json={
                "currency": "AZN",
                "customer_name": "Aysel",
                "lines": [
                    {"sku": "X", "qty": 2, "unit_price_minor": 150, "name": "Item X"},
                ],
            },
        )
    since = datetime(2026, 1, 1, tzinfo=UTC)
    orders = await adapter.pull_orders(since=since)
    assert len(orders) == 1
    order = orders[0]
    assert order.channel_order_id.startswith("MOCK-ORD-")
    assert order.totals.grand_total_minor == 300  # 150 * 2
    assert order.customer is not None and order.customer.name == "Aysel"
    assert order.status is OrderStatus.PENDING


@pytest.mark.integration
async def test_acknowledge_order_round_trip(
    adapter_with_mock: tuple[MockMarketplaceAdapter, object],
) -> None:
    adapter, mock = adapter_with_mock
    async with _client_for_app(mock) as direct:
        order = (
            await direct.post(
                "/_test/orders",
                json={
                    "currency": "AZN",
                    "lines": [{"sku": "Y", "qty": 1, "unit_price_minor": 100, "name": "Y"}],
                },
            )
        ).json()
    await adapter.acknowledge_order(channel_order_id=order["channel_order_id"], status="confirmed")

    # The mock recorded the ack — verify via the store directly.
    store = mock.state.store  # type: ignore[attr-defined]
    assert store.last_ack(order["channel_order_id"]) == "confirmed"


@pytest.mark.integration
async def test_acknowledge_unknown_order_raises_permanent() -> None:
    """A 404 from the channel is a payload problem (the id doesn't exist) —
    not retryable. Adapter must surface :class:`AdapterPermanentError`."""
    mock = create_mock_app()
    client = _client_for_app(mock)
    adapter = MockMarketplaceAdapter(
        MockMarketplaceConfig(base_url="http://mock-marketplace"), client=client
    )
    try:
        with pytest.raises(AdapterPermanentError):
            await adapter.acknowledge_order(channel_order_id="ghost", status="confirmed")
    finally:
        await adapter.aclose()


# ----------------------------------------------------------------
# Error classification from synthetic responses (no mock server needed)
# ----------------------------------------------------------------


class _FakeTransport(httpx.AsyncBaseTransport):
    """Static HTTP responder — every request returns the same fixed reply."""

    def __init__(
        self, status_code: int, *, body: str = "boom", headers: dict[str, str] | None = None
    ) -> None:
        self._status = status_code
        self._body = body.encode()
        self._headers = headers or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status, content=self._body, headers=self._headers)


def _adapter_with_transport(transport: httpx.AsyncBaseTransport) -> MockMarketplaceAdapter:
    return MockMarketplaceAdapter(
        MockMarketplaceConfig(base_url="http://upstream"),
        client=httpx.AsyncClient(transport=transport, base_url="http://upstream"),
    )


@pytest.mark.integration
async def test_5xx_maps_to_retryable() -> None:
    adapter = _adapter_with_transport(_FakeTransport(503))
    try:
        with pytest.raises(AdapterRetryableError):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_429_maps_to_rate_limit_with_retry_after() -> None:
    adapter = _adapter_with_transport(_FakeTransport(429, headers={"Retry-After": "13"}))
    try:
        with pytest.raises(AdapterRateLimitError) as exc_info:
            await adapter.push_stock(sku="X", qty=1)
        assert exc_info.value.retry_after_seconds == 13.0
    finally:
        await adapter.aclose()


@pytest.mark.integration
@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_codes_map_to_auth_error(status_code: int) -> None:
    adapter = _adapter_with_transport(_FakeTransport(status_code))
    try:
        with pytest.raises(AdapterAuthError):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_400_maps_to_permanent() -> None:
    adapter = _adapter_with_transport(_FakeTransport(400, body="bad shape"))
    try:
        with pytest.raises(AdapterPermanentError, match="bad shape"):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_fetch_listing_5xx_maps_to_retryable() -> None:
    """fetch_listing classifies non-404 errors like every other call — only a
    404 is special (→ ``None``)."""
    adapter = _adapter_with_transport(_FakeTransport(503))
    try:
        with pytest.raises(AdapterRetryableError):
            await adapter.fetch_listing(sku="X")
    finally:
        await adapter.aclose()


class _RaisingTransport(httpx.AsyncBaseTransport):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise self._exc


@pytest.mark.integration
async def test_timeout_maps_to_retryable() -> None:
    adapter = _adapter_with_transport(_RaisingTransport(httpx.ReadTimeout("slow")))
    try:
        with pytest.raises(AdapterRetryableError, match="timeout"):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()


@pytest.mark.integration
async def test_transport_error_maps_to_retryable() -> None:
    adapter = _adapter_with_transport(_RaisingTransport(httpx.ConnectError("dead")))
    try:
        with pytest.raises(AdapterRetryableError, match="transport"):
            await adapter.push_stock(sku="X", qty=1)
    finally:
        await adapter.aclose()
