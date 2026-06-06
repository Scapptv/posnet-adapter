"""MockBazarAdapter (Part V V1.1) — the 2nd concrete channel adapter.

Implements :class:`~libs.adapter.ChannelAdapter` against Mock Bazar's
deliberately-different wire surface. Its whole reason to exist: prove that
"add a channel = write one adapter + a contract test" holds even when the
channel's shape diverges from mock-marketplace — nested ``price``/``totals``
objects, a list ``category_path``, ``PUT`` verbs, ``/products``+``/sales``
paths, and a different status vocabulary (``live``/``new`` vs ``active``/
``pending``). All of that diversity is absorbed *here*, in the mapping; the
canonical model + the rest of the engine never see it.

Error classification + httpx-client injection mirror ``MockMarketplaceAdapter``
exactly (the shared contract every adapter inherits).
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

from ...sync.channel_config import parse_channel_config

CODE = "mock-bazar"

# Bazar listing state <-> hub channel-listing status vocabulary.
_STATE_TO_STATUS: dict[str, str] = {"live": "active", "hold": "pending", "denied": "rejected"}
# Bazar sale state <-> canonical order status.
_SALE_TO_ORDER: dict[str, str] = {
    "new": "pending",
    "accepted": "confirmed",
    "shipped": "fulfilled",
    "void": "cancelled",
}
# canonical ack status (hub speaks this) -> Bazar sale state.
_ACK_TO_SALE: dict[str, str] = {
    "pending": "new",
    "confirmed": "accepted",
    "fulfilled": "shipped",
    "cancelled": "void",
}


@dataclass(frozen=True, slots=True)
class MockBazarConfig:
    base_url: str
    timeout_seconds: float = 5.0


class MockBazarAdapter:
    """One adapter instance per channel row. Stateless; safe to share."""

    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        code=CODE,
        name="Mock Bazar",
        auth_kind="hmac",
        supports_push_listing=True,
        supports_push_stock=True,
        supports_push_price=True,
        supports_fetch_listing=True,
        supports_pull_orders=True,
        supports_webhook_orders=True,
        webhook_signature_header="X-Bazar-Signature",
        rate_limit_rps=10,
        rate_limit_burst=20,
        tags=frozenset({"mock", "marketplace"}),
    )

    def __init__(self, config: MockBazarConfig, *, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @classmethod
    def from_channel(cls, channel: Any, *, settings: Any) -> MockBazarAdapter:
        """Construct for a channel row (H6 wiring). Base URL from
        ``channel.config['base_url']`` or ``settings.mock_bazar_base_url``."""
        base_url = parse_channel_config(channel.config).base_url or settings.mock_bazar_base_url
        return cls(MockBazarConfig(base_url=str(base_url)))

    # ----------------------------------------------------------------
    # Outbound — push
    # ----------------------------------------------------------------

    async def push_listing(
        self, products: Sequence[CanonicalProduct]
    ) -> Sequence[ChannelListingResult]:
        results: list[ChannelListingResult] = []
        for product in products:
            payload = {
                "merchant_sku": product.sku,
                "gtin": product.barcode,
                "title": product.name,
                "attrs": product.attributes,
                "category_path": list(product.category_path),
                "price": {"amount_minor": product.price_minor, "currency": product.currency},
                "quantity": product.stock_qty,
            }
            data = await self._request("POST", "/products", json=payload)
            results.append(
                ChannelListingResult(
                    sku=str(data["merchant_sku"]),
                    external_listing_id=str(data["ref"]),
                    status=_STATE_TO_STATUS.get(str(data["state"]), "pending"),
                )
            )
        return results

    async def push_stock(self, *, sku: str, qty: int) -> None:
        await self._request("PUT", f"/products/{sku}/quantity", json={"quantity": qty})

    async def push_price(self, *, sku: str, price: CanonicalPrice) -> None:
        await self._request(
            "PUT",
            f"/products/{sku}/price",
            json={"price": {"amount_minor": price.price_minor, "currency": price.currency}},
        )

    async def fetch_listing(self, *, sku: str) -> ChannelListingSnapshot | None:
        response = await self._send("GET", f"/products/{sku}")
        if response.status_code == 404:
            return None
        self._raise_for_status(response)
        data = response.json()
        return ChannelListingSnapshot(
            sku=str(data["merchant_sku"]),
            stock=int(data["quantity"]),
            price_minor=int(data["price"]["amount_minor"]),
            currency=str(data["price"]["currency"]),
            external_listing_id=str(data["ref"]),
            status=_STATE_TO_STATUS.get(str(data["state"]), "pending"),
        )

    # ----------------------------------------------------------------
    # Inbound — pull / ack
    # ----------------------------------------------------------------

    async def pull_orders(self, *, since: datetime) -> Sequence[CanonicalOrder]:
        data = await self._request("GET", "/sales", params={"from": since.isoformat()})
        return [self._normalise_sale(raw) for raw in data["sales"]]

    async def acknowledge_order(self, *, channel_order_id: str, status: str) -> None:
        await self._request(
            "POST",
            f"/sales/{channel_order_id}/state",
            json={"state": _ACK_TO_SALE.get(status, "new")},
        )

    # ----------------------------------------------------------------
    # Mapping
    # ----------------------------------------------------------------

    def map_category(self, canonical_category: Sequence[str]) -> str:
        return "/".join(canonical_category)

    def normalize_webhook(self, *, body: bytes, headers: Mapping[str, str]) -> CanonicalOrder:
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterPermanentError(f"webhook body is not JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise AdapterPermanentError("webhook body must be a JSON object")
        return self._normalise_sale(raw)

    @staticmethod
    def _normalise_sale(raw: dict[str, Any]) -> CanonicalOrder:
        totals = raw["totals"]
        currency = str(totals["currency"])
        lines = tuple(
            CanonicalOrderLine(
                sku=str(item["merchant_sku"]),
                name=str(item["label"]),
                qty=int(item["units"]),
                unit_price_minor=int(item["unit_amount_minor"]),
                currency=currency,
            )
            for item in raw["items"]
        )
        buyer = raw.get("buyer") or {}
        customer = CanonicalCustomer(name=str(buyer["name"])) if buyer.get("name") else None
        return CanonicalOrder(
            channel_order_id=str(raw["ref"]),
            lines=lines,
            totals=CanonicalTotals(
                subtotal_minor=int(totals["sub_amount_minor"]),
                grand_total_minor=int(totals["grand_amount_minor"]),
                currency=currency,
            ),
            status=OrderStatus(_SALE_TO_ORDER.get(str(raw.get("state", "new")), "pending")),
            customer=customer,
        )

    # ----------------------------------------------------------------
    # Internals — HTTP wrapper + error classification (shared shape)
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
