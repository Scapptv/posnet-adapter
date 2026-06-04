"""Mock marketplace request/response schemas (AI-2.5.3).

Pydantic v2; strict (extra='forbid') so the adapter contract surfaces
spelling/shape mistakes loudly instead of silently dropping fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ListingCreate(BaseModel):
    """Payload the adapter sends to ``POST /listings``."""

    model_config = ConfigDict(extra="forbid")

    seller_sku: str = Field(min_length=1, max_length=100)
    barcode: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    attributes: dict[str, str] = Field(default_factory=dict)
    category: str | None = Field(default=None, max_length=500)
    price_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    stock: int = Field(ge=0)


class ListingResponse(BaseModel):
    """What ``POST /listings`` returns. The channel's external id is what
    the adapter persists into ``channel_listings.external_listing_id``."""

    external_listing_id: str
    seller_sku: str
    status: Literal["active", "pending", "rejected"]


class StockUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qty: int = Field(ge=0)


class PriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class OrderLineDTO(BaseModel):
    sku: str
    qty: int
    unit_price_minor: int
    name: str


class OrderDTO(BaseModel):
    """Channel order shape. The adapter normalises this into
    :class:`libs.canonical_model.CanonicalOrder` on ingest."""

    channel_order_id: str
    created_at: datetime
    currency: str
    lines: list[OrderLineDTO]
    subtotal_minor: int
    grand_total_minor: int
    customer_name: str | None = None
    status: Literal["pending", "confirmed", "fulfilled", "cancelled"] = "pending"


class OrdersPage(BaseModel):
    orders: list[OrderDTO]


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "confirmed", "fulfilled", "cancelled"]


class OrderSeedRequest(BaseModel):
    """Test hook: create a fake order in the mock so adapter pull/ack tests
    have something to read. NOT a real channel endpoint."""

    model_config = ConfigDict(extra="forbid")

    lines: list[OrderLineDTO]
    currency: str = Field(min_length=3, max_length=3)
    customer_name: str | None = None
