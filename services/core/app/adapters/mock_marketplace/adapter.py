"""MockMarketplaceAdapter (AI-2.5.3, roadmap §17.5).

Implements :class:`~libs.adapter.ChannelAdapter` against the mock marketplace
HTTP surface. Two things this adapter establishes for later concrete
adapters:

1. **HTTP error → AdapterError classification** — the same mapping every
   real adapter inherits: 401/403 → Auth, 429 → RateLimit (with Retry-After),
   4xx → Permanent, 5xx → Retryable, network/timeout → Retryable.
2. **HTTPX client injection** — production wiring passes a configured
   ``httpx.AsyncClient`` (timeouts, retries, telemetry); tests pass one wired
   to an ASGI transport so the call never touches a real socket.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

import httpx

from libs.adapter import (
    AdapterAuthError,
    AdapterCapabilities,
    AdapterPermanentError,
    AdapterRateLimitError,
    AdapterRetryableError,
    ChannelListingResult,
    ChannelListingSnapshot,
)
from libs.canonical_model import (
    CanonicalCustomer,
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalPrice,
    CanonicalProduct,
    CanonicalTotals,
    OrderStatus,
)

CODE = "mock-marketplace"


@dataclass(frozen=True, slots=True)
class MockMarketplaceConfig:
    """Per-adapter-instance settings."""

    base_url: str
    timeout_seconds: float = 5.0


class MockMarketplaceAdapter:
    """One adapter instance per channel row. Stateless; safe to share."""

    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        code=CODE,
        name="Mock Marketplace",
        auth_kind="hmac",
        supports_push_listing=True,
        supports_push_stock=True,
        supports_push_price=True,
        supports_fetch_listing=True,
        supports_pull_orders=True,
        supports_webhook_orders=True,
        webhook_signature_header="X-Mock-Signature",
        rate_limit_rps=10,
        rate_limit_burst=20,
        tags=frozenset({"mock", "marketplace"}),
    )

    def __init__(
        self, config: MockMarketplaceConfig, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        )

    async def aclose(self) -> None:
        """Release the underlying httpx client. Production wiring calls this
        on app shutdown; tests use a fixture that wraps it."""
        await self._client.aclose()

    # ----------------------------------------------------------------
    # Outbound — push
    # ----------------------------------------------------------------

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        results: list[ChannelListingResult] = []
        for product in products:
            payload = {
                "seller_sku": product.sku,
                "barcode": product.barcode,
                "name": product.name,
                "attributes": product.attributes,
                "category": "/".join(product.category_path) or None,
                "price_minor": product.price_minor,
                "currency": product.currency,
                "stock": product.stock_qty,
            }
            data = await self._request("POST", "/listings", json=payload)
            results.append(
                ChannelListingResult(
                    sku=str(data["seller_sku"]),
                    external_listing_id=str(data["external_listing_id"]),
                    status=str(data["status"]),
                )
            )
        return results

    async def push_stock(self, *, sku: str, qty: int) -> None:
        await self._request("PATCH", f"/listings/{sku}/stock", json={"qty": qty})

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        await self._request(
            "PATCH",
            f"/listings/{sku}/price",
            json={"price_minor": price.price_minor, "currency": price.currency},
        )

    async def fetch_listing(self, *, sku: str) -> ChannelListingSnapshot | None:
        """Read the channel's current listing state for reconciliation. A 404
        means the SKU isn't listed here (returns ``None``); other non-2xx codes
        classify into the usual ``AdapterError`` hierarchy."""
        response = await self._send("GET", f"/listings/{sku}")
        if response.status_code == 404:
            return None
        self._raise_for_status(response)
        data = response.json()
        return ChannelListingSnapshot(
            sku=str(data["seller_sku"]),
            stock=int(data["stock"]),
            price_minor=int(data["price_minor"]),
            currency=str(data["currency"]),
            external_listing_id=str(data["external_listing_id"]),
            status=str(data["status"]),
        )

    # ----------------------------------------------------------------
    # Inbound — pull / ack
    # ----------------------------------------------------------------

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        data = await self._request("GET", "/orders", params={"since": since.isoformat()})
        return [self._normalise_order(raw) for raw in data["orders"]]

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        await self._request("POST", f"/orders/{channel_order_id}/ack", json={"status": status})

    # ----------------------------------------------------------------
    # Mapping
    # ----------------------------------------------------------------

    def map_category(self, canonical_category: Sequence[str]) -> str:
        """Mock channel takes the canonical path joined by ``/`` verbatim.
        Real channels (Trendyol etc.) would hold a lookup table here."""
        return "/".join(canonical_category)

    def normalize_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> CanonicalOrder:
        """Mock channel posts the same JSON shape ``GET /orders`` would
        return — single :class:`OrderDTO` per delivery. The webhook endpoint
        verified the HMAC before this call (``headers`` carry the original
        request headers in case a future channel needs request-scoped
        context like timestamps)."""
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterPermanentError(f"webhook body is not JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise AdapterPermanentError("webhook body must be a JSON object")
        return self._normalise_order(raw)

    # ----------------------------------------------------------------
    # Internals — HTTP wrapper + error classification
    # ----------------------------------------------------------------

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise AdapterRetryableError(f"timeout: {exc}") from exc
        except httpx.TransportError as exc:
            raise AdapterRetryableError(f"transport: {exc}") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 500:
            raise AdapterRetryableError(f"channel {response.status_code}: {response.text[:200]}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise AdapterRateLimitError(
                "channel rate limited",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code in (401, 403):
            raise AdapterAuthError(f"channel rejected credentials: {response.text[:200]}")
        if response.status_code >= 400:
            raise AdapterPermanentError(f"channel {response.status_code}: {response.text[:200]}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._send(method, path, **kwargs)
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _normalise_order(raw: dict[str, Any]) -> CanonicalOrder:
        lines = tuple(
            CanonicalOrderLine(
                sku=str(line["sku"]),
                name=str(line["name"]),
                qty=int(line["qty"]),
                unit_price_minor=int(line["unit_price_minor"]),
                currency=str(raw["currency"]),
            )
            for line in raw["lines"]
        )
        customer = (
            CanonicalCustomer(name=str(raw["customer_name"])) if raw.get("customer_name") else None
        )
        return CanonicalOrder(
            channel_order_id=str(raw["channel_order_id"]),
            lines=lines,
            totals=CanonicalTotals(
                subtotal_minor=int(raw["subtotal_minor"]),
                grand_total_minor=int(raw["grand_total_minor"]),
                currency=str(raw["currency"]),
            ),
            status=OrderStatus(raw.get("status", "pending")),
            customer=customer,
        )
