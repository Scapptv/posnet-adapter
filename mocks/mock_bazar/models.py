"""Mock Bazar (2nd marketplace) wire schemas (Part V V1.1).

A *deliberately differently-shaped* marketplace stand-in — the point of the
2nd adapter is to prove the canonical model + ``ChannelAdapter`` contract absorb
channel diversity, not just mock-marketplace's exact shape. So Bazar uses:
nested ``price``/``totals`` objects (not flat ``price_minor``), a list
``category_path`` (not a joined string), a different status vocabulary
(``live``/``hold``/``denied``), and renamed fields (``merchant_sku``, ``gtin``,
``quantity``, ``ref``). The adapter's job is to map all of that to/from canonical.

Strict (``extra='forbid'``) on inbound so a mapping mistake fails loudly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BazarState = Literal["live", "hold", "denied"]
SaleState = Literal["new", "accepted", "shipped", "void"]


class Money(BaseModel):
    """Nested money object — the key structural difference from mock-marketplace."""

    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class ProductUpsert(BaseModel):
    """Payload the adapter sends to ``POST /products``."""

    model_config = ConfigDict(extra="forbid")

    merchant_sku: str = Field(min_length=1, max_length=100)
    gtin: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    attrs: dict[str, str] = Field(default_factory=dict)
    category_path: list[str] = Field(default_factory=list)
    price: Money
    quantity: int = Field(ge=0)


class ProductRef(BaseModel):
    """What ``POST /products`` returns."""

    ref: str
    merchant_sku: str
    state: BazarState


class ProductView(BaseModel):
    """Full Bazar-side view (``GET /products/{sku}``) for reconciliation."""

    ref: str
    merchant_sku: str
    state: BazarState
    quantity: int
    price: Money


class QuantityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=0)


class PriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Money


class SaleItem(BaseModel):
    merchant_sku: str
    units: int
    unit_amount_minor: int
    label: str


class SaleTotals(BaseModel):
    sub_amount_minor: int
    grand_amount_minor: int
    currency: str


class SaleBuyer(BaseModel):
    name: str | None = None


class Sale(BaseModel):
    """Bazar order shape — nested ``totals``/``buyer``, ``items`` not ``lines``."""

    ref: str
    placed_at: datetime
    items: list[SaleItem]
    totals: SaleTotals
    buyer: SaleBuyer = Field(default_factory=SaleBuyer)
    state: SaleState = "new"


class SalesPage(BaseModel):
    sales: list[Sale]


class StateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: SaleState


class SaleSeedRequest(BaseModel):
    """Test hook — not a real Bazar endpoint."""

    model_config = ConfigDict(extra="forbid")

    items: list[SaleItem]
    currency: str = Field(min_length=3, max_length=3)
    buyer_name: str | None = None
