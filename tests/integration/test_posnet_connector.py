"""AI-2.8.2 — :class:`PosnetConnector` over the HTTP mock Posnet.

The POS-side mirror of ``test_mock_marketplace_adapter``: drive the real-shaped
connector against the in-process mock (``GET /catalog`` + ``POST /orders``) for
the happy paths, then the same HTTP-error -> ``AdapterError`` classification via
synthetic transports. The live Posnet swaps in on this exact contract.
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
)
from libs.canonical_model import (
    CanonicalCustomer,
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalTotals,
    OrderStatus,
)
from mocks.mock_posnet import MockPosnetStore, create_app
from mocks.mock_posnet.models import CatalogProduct
from services.core.app.adapters.posnet import PosnetConfig, PosnetConnector

BASE = "http://posnet"


def _client_for_app(app: object) -> httpx.AsyncClient:
    """An httpx client wired straight to the FastAPI app's ASGI transport — no
    socket, no port."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url=BASE)


def _an_order() -> CanonicalOrder:
    return CanonicalOrder(
        channel_order_id="CH-ORD-1",
        lines=(
            CanonicalOrderLine(
                sku="SKU-1", name="Cola", qty=2, unit_price_minor=150, currency="AZN"
            ),
        ),
        totals=CanonicalTotals(subtotal_minor=300, grand_total_minor=300, currency="AZN"),
        status=OrderStatus.PENDING,
        customer=CanonicalCustomer(name="Aysel"),
    )


@pytest.fixture
async def connector_with_store() -> AsyncIterator[tuple[PosnetConnector, MockPosnetStore]]:
    store = MockPosnetStore()
    app = create_app(store)
    connector = PosnetConnector(PosnetConfig(base_url=BASE), client=_client_for_app(app))
    try:
        yield connector, store
    finally:
        await connector.aclose()


# ----------------------------------------------------------------
# Happy paths against the mock
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_pull_catalog_maps_to_canonical_products(
    connector_with_store: tuple[PosnetConnector, MockPosnetStore],
) -> None:
    connector, store = connector_with_store
    store.seed(
        CatalogProduct(
            sku="SKU-1",
            name="Cola 1L",
            barcode="8690000000001",
            category_path=["Drinks", "Soda"],
            price_minor=250,
            currency="AZN",
            stock=12,
        ),
        CatalogProduct(
            sku="SKU-2",
            name="Water 0.5L",
            price_minor=80,
            currency="AZN",
            stock=40,
        ),
    )

    products = await connector.pull_catalog()

    assert [p.sku for p in products] == ["SKU-1", "SKU-2"]
    cola = products[0]
    assert cola.name == "Cola 1L"
    assert cola.barcode == "8690000000001"
    assert cola.category_path == ("Drinks", "Soda")  # list -> tuple
    assert cola.price_minor == 250
    assert cola.currency == "AZN"
    assert cola.stock_qty == 12
    # Optional fields the POS omits stay at canonical defaults.
    assert products[1].barcode is None
    assert products[1].category_path == ()


@pytest.mark.integration
async def test_pull_catalog_empty_when_unseeded(
    connector_with_store: tuple[PosnetConnector, MockPosnetStore],
) -> None:
    connector, _ = connector_with_store
    assert list(await connector.pull_catalog()) == []


@pytest.mark.integration
async def test_push_order_records_in_pos(
    connector_with_store: tuple[PosnetConnector, MockPosnetStore],
) -> None:
    connector, store = connector_with_store
    await connector.push_order(_an_order())

    assert len(store.received_orders) == 1
    recorded = store.received_orders[0]
    assert recorded["channel_order_id"] == "CH-ORD-1"
    # The full canonical order rides along (OrderWrite allows extra) — the POS
    # gets lines/totals/customer, not just the id.
    assert recorded["totals"]["grand_total_minor"] == 300
    assert recorded["lines"][0]["sku"] == "SKU-1"
    assert recorded["customer"]["name"] == "Aysel"


# ----------------------------------------------------------------
# Auth seam (ADR-0022) — the real-Posnet swap point
# ----------------------------------------------------------------


@pytest.mark.integration
async def test_auth_headers_ride_on_the_client() -> None:
    """Config auth headers apply to every request via the connector's own httpx
    client — scheme-agnostic (Bearer, API-key, ...), the real-Posnet swap seam.
    The mock path (no headers) is exercised by every other test here."""
    connector = PosnetConnector(
        PosnetConfig(base_url=BASE, auth_headers={"Authorization": "Bearer secret-token"})
    )
    try:
        assert connector._client.headers["Authorization"] == "Bearer secret-token"
    finally:
        await connector.aclose()


# ----------------------------------------------------------------
# HTTP-error classification (synthetic transports, no mock server)
# ----------------------------------------------------------------


class _FakeTransport(httpx.AsyncBaseTransport):
    """Static responder — every request returns the same fixed reply."""

    def __init__(
        self, status_code: int, *, body: str = "boom", headers: dict[str, str] | None = None
    ) -> None:
        self._status = status_code
        self._body = body.encode()
        self._headers = headers or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status, content=self._body, headers=self._headers)


class _RaisingTransport(httpx.AsyncBaseTransport):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise self._exc


def _connector_with_transport(transport: httpx.AsyncBaseTransport) -> PosnetConnector:
    return PosnetConnector(
        PosnetConfig(base_url=BASE),
        client=httpx.AsyncClient(transport=transport, base_url=BASE),
    )


@pytest.mark.integration
async def test_5xx_maps_to_retryable() -> None:
    connector = _connector_with_transport(_FakeTransport(503))
    try:
        with pytest.raises(AdapterRetryableError):
            await connector.pull_catalog()
    finally:
        await connector.aclose()


@pytest.mark.integration
async def test_429_maps_to_rate_limit_with_retry_after() -> None:
    connector = _connector_with_transport(_FakeTransport(429, headers={"Retry-After": "13"}))
    try:
        with pytest.raises(AdapterRateLimitError) as exc_info:
            await connector.pull_catalog()
        assert exc_info.value.retry_after_seconds == 13.0
    finally:
        await connector.aclose()


@pytest.mark.integration
@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_codes_map_to_auth_error(status_code: int) -> None:
    connector = _connector_with_transport(_FakeTransport(status_code))
    try:
        with pytest.raises(AdapterAuthError):
            await connector.pull_catalog()
    finally:
        await connector.aclose()


@pytest.mark.integration
async def test_400_maps_to_permanent() -> None:
    connector = _connector_with_transport(_FakeTransport(400, body="bad shape"))
    try:
        with pytest.raises(AdapterPermanentError, match="bad shape"):
            await connector.push_order(_an_order())
    finally:
        await connector.aclose()


@pytest.mark.integration
async def test_timeout_maps_to_retryable() -> None:
    connector = _connector_with_transport(_RaisingTransport(httpx.ReadTimeout("slow")))
    try:
        with pytest.raises(AdapterRetryableError, match="timeout"):
            await connector.pull_catalog()
    finally:
        await connector.aclose()


@pytest.mark.integration
async def test_transport_error_maps_to_retryable() -> None:
    connector = _connector_with_transport(_RaisingTransport(httpx.ConnectError("dead")))
    try:
        with pytest.raises(AdapterRetryableError, match="transport"):
            await connector.pull_catalog()
    finally:
        await connector.aclose()
