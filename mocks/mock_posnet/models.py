"""HTTP mock Posnet request/response schemas (AI-2.8.2).

A stand-in for the real Posnet POS over HTTP — its own wire shape (not the
canonical model), so the connector's mapping is exercised exactly like a real
Posnet API would force. Strict (``extra='forbid'``) on the catalog so a shape
mistake fails loudly; the order write-back allows extra so the connector can
post the full canonical order without the mock pinning every field.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CatalogProduct(BaseModel):
    """One product as the (mock) Posnet serves it."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    barcode: str | None = Field(default=None, max_length=100)
    category_path: list[str] = Field(default_factory=list)
    price_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    stock: int = Field(ge=0)


class CatalogResponse(BaseModel):
    products: list[CatalogProduct]


class OrderWrite(BaseModel):
    """Order write-back the connector posts. Accepts the full canonical order
    (extra allowed) but pins the id so the mock can key on it."""

    model_config = ConfigDict(extra="allow")

    channel_order_id: str = Field(min_length=1)
