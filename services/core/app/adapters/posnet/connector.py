"""PosnetConnector (AI-2.8.2, ADR-0021) — the real-shaped POS source.

Implements :class:`~libs.pos_source.PosSourceAdapter` over HTTP against the
(mock) Posnet API. It is the POS-side mirror of ``MockMarketplaceAdapter``:
same httpx-client injection, same HTTP-error -> ``AdapterError`` classification,
the canonical model as the wire-facing format. Today it talks to
``mocks.mock_posnet`` (``GET /catalog`` + ``POST /orders``); the real Posnet
swap is a base-URL change once the live interface/auth is known — no call-site
churn, because everything upstream depends only on the ``PosSourceAdapter``
contract.

Errors reuse the ``libs.adapter`` hierarchy on purpose: one error vocabulary
across both sides of the hub, so the sync engine / ingest classify POS failures
(auth, rate-limit, retryable, permanent) exactly as it does channel failures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from libs.adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRateLimitError,
    AdapterRetryableError,
)
from libs.canonical_model import CanonicalOrder, CanonicalProduct
from libs.pos_source import PosSourceCapabilities

CODE = "posnet"


@dataclass(frozen=True, slots=True)
class PosnetConfig:
    """Per-connection settings (one Posnet per tenant)."""

    base_url: str
    timeout_seconds: float = 5.0


class PosnetConnector:
    """One connector instance per Posnet connection. Stateless; safe to share."""

    capabilities: ClassVar[PosSourceCapabilities] = PosSourceCapabilities(
        code=CODE,
        name="Posnet",
        supports_pull_catalog=True,
        supports_push_order=True,
    )

    def __init__(self, config: PosnetConfig, *, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        )

    async def aclose(self) -> None:
        """Release the underlying httpx client (production wiring calls this on
        app shutdown; tests wrap it in a fixture)."""
        await self._client.aclose()

    # ----------------------------------------------------------------
    # PosSourceAdapter
    # ----------------------------------------------------------------

    async def pull_catalog(self) -> Sequence[CanonicalProduct]:
        data = await self._request("GET", "/catalog")
        return [self._to_canonical(raw) for raw in data["products"]]

    async def push_order(self, order: CanonicalOrder) -> None:
        await self._request("POST", "/orders", json=order.model_dump(mode="json"))

    # ----------------------------------------------------------------
    # Mapping
    # ----------------------------------------------------------------

    @staticmethod
    def _to_canonical(raw: dict[str, Any]) -> CanonicalProduct:
        """Map one Posnet catalog row -> canonical product. The single place the
        POS wire shape is known; everything downstream sees only canonical."""
        return CanonicalProduct(
            sku=str(raw["sku"]),
            barcode=raw.get("barcode"),
            name=str(raw["name"]),
            category_path=tuple(raw.get("category_path", ())),
            price_minor=int(raw["price_minor"]),
            currency=str(raw["currency"]),
            stock_qty=int(raw["stock"]),
        )

    # ----------------------------------------------------------------
    # Internals — HTTP wrapper + error classification (mirrors the channel side)
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
            raise AdapterRetryableError(f"posnet {response.status_code}: {response.text[:200]}")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise AdapterRateLimitError(
                "posnet rate limited",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code in (401, 403):
            raise AdapterAuthError(f"posnet rejected credentials: {response.text[:200]}")
        if response.status_code >= 400:
            raise AdapterPermanentError(f"posnet {response.status_code}: {response.text[:200]}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._send(method, path, **kwargs)
        self._raise_for_status(response)
        return response.json()
