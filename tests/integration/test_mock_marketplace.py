"""AI-2.5.3 — mock marketplace service smoke tests.

The mock is a real FastAPI app; these tests exercise its HTTP surface end-to-
end. The adapter contract test (``test_mock_marketplace_adapter.py``) goes the
other way — driving the same app through the adapter abstraction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from mocks.mock_marketplace import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.integration
def test_post_listing_returns_external_id(client: TestClient) -> None:
    response = client.post(
        "/listings",
        json={
            "seller_sku": "SKU-1",
            "name": "Coca Cola",
            "attributes": {},
            "price_minor": 300,
            "currency": "AZN",
            "stock": 10,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["seller_sku"] == "SKU-1"
    assert body["external_listing_id"].startswith("MOCK-")
    assert body["status"] == "active"


@pytest.mark.integration
def test_post_listing_is_idempotent_per_sku(client: TestClient) -> None:
    """Two POSTs with the same SKU return the same external id — matches the
    contract the adapter test will assert."""
    payload = {
        "seller_sku": "SKU-IDEMP",
        "name": "P",
        "attributes": {},
        "price_minor": 100,
        "currency": "AZN",
        "stock": 1,
    }
    first = client.post("/listings", json=payload).json()
    second = client.post("/listings", json=payload).json()
    assert first["external_listing_id"] == second["external_listing_id"]


@pytest.mark.integration
def test_patch_stock_updates_listing(client: TestClient) -> None:
    client.post(
        "/listings",
        json={
            "seller_sku": "STK",
            "name": "P",
            "attributes": {},
            "price_minor": 1,
            "currency": "AZN",
            "stock": 5,
        },
    )
    response = client.patch("/listings/STK/stock", json={"qty": 17})
    assert response.status_code == 200
    assert response.json()["seller_sku"] == "STK"


@pytest.mark.integration
def test_patch_stock_unknown_sku_returns_404(client: TestClient) -> None:
    response = client.patch("/listings/UNKNOWN/stock", json={"qty": 1})
    assert response.status_code == 404


@pytest.mark.integration
def test_patch_price_updates_listing(client: TestClient) -> None:
    client.post(
        "/listings",
        json={
            "seller_sku": "PRC",
            "name": "P",
            "attributes": {},
            "price_minor": 100,
            "currency": "AZN",
            "stock": 1,
        },
    )
    response = client.patch("/listings/PRC/price", json={"price_minor": 250, "currency": "AZN"})
    assert response.status_code == 200


@pytest.mark.integration
def test_orders_endpoint_filters_by_since(client: TestClient) -> None:
    """Seed two orders, page only by ``since`` covers both, then a later
    ``since`` filters out the early one."""
    client.post(
        "/_test/orders",
        json={
            "currency": "AZN",
            "lines": [{"sku": "A", "qty": 1, "unit_price_minor": 100, "name": "A"}],
        },
    )

    now = datetime.now(UTC)
    response = client.get("/orders", params={"since": (now - timedelta(hours=1)).isoformat()})
    assert response.status_code == 200
    assert len(response.json()["orders"]) >= 1

    later = (now + timedelta(hours=1)).isoformat()
    assert client.get("/orders", params={"since": later}).json()["orders"] == []


@pytest.mark.integration
def test_ack_records_status(client: TestClient) -> None:
    order = client.post(
        "/_test/orders",
        json={
            "currency": "AZN",
            "lines": [{"sku": "A", "qty": 1, "unit_price_minor": 100, "name": "A"}],
        },
    ).json()
    response = client.post(f"/orders/{order['channel_order_id']}/ack", json={"status": "confirmed"})
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


@pytest.mark.integration
def test_ack_unknown_order_is_404(client: TestClient) -> None:
    response = client.post("/orders/no-such-id/ack", json={"status": "confirmed"})
    assert response.status_code == 404


@pytest.mark.integration
async def test_create_app_is_isolated_per_instance() -> None:
    """Each ``create_app`` call gets its own store — tests don't leak state."""
    transport_a = httpx.ASGITransport(app=create_app())
    transport_b = httpx.ASGITransport(app=create_app())
    async with (
        httpx.AsyncClient(transport=transport_a, base_url="http://app") as a,
        httpx.AsyncClient(transport=transport_b, base_url="http://app") as b,
    ):
        await a.post(
            "/listings",
            json={
                "seller_sku": "ISO",
                "name": "P",
                "attributes": {},
                "price_minor": 1,
                "currency": "AZN",
                "stock": 1,
            },
        )
        # B has never seen ISO — stock update is 404.
        response = await b.patch("/listings/ISO/stock", json={"qty": 5})
    assert response.status_code == 404
