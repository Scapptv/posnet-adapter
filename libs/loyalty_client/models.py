"""Pydantic v2 request/response models for the Paylo loyalty API.

The shapes here mirror Paylo's `/api/v1/pos/*` contract exactly. Field names use
``snake_case`` because Paylo's REST surface is snake-cased by design (see Paylo
API.md §0). Any drift from these shapes is a contract breach — Paylo's tests pin
its own side, this lib pins ours.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#
# Request models
#


class LookupCustomerRequest(BaseModel):
    """POST /api/v1/pos/customer/lookup"""

    model_config = ConfigDict(extra="forbid")

    qr: str = Field(..., min_length=3, max_length=192)


class PreviewSaleRequest(BaseModel):
    """POST /api/v1/pos/sale/preview"""

    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(..., gt=0)
    sale_amount_cents: int = Field(..., ge=1, le=99_999_999)
    use_bonus: bool = False
    redeem_cents: int | None = Field(default=None, ge=0, le=99_999_999)
    branch_id: int | None = Field(default=None, gt=0)


class CompleteSaleRequest(BaseModel):
    """POST /api/v1/pos/sale

    ``receipt_no`` is the merchant-scoped idempotency key at the domain level.
    Paylo's unique ``(merchant_id, receipt_no)`` constraint guarantees that even
    if our Idempotency-Key header cache expires, a retried sale with the same
    receipt_no still de-duplicates server-side.
    """

    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(..., gt=0)
    sale_amount_cents: int = Field(..., ge=1, le=99_999_999)
    receipt_no: str = Field(..., pattern=r"^[A-Za-z0-9_\-]{1,64}$")
    branch_id: int | None = Field(default=None, gt=0)
    use_bonus: bool = False
    redeem_cents: int | None = Field(default=None, ge=0, le=99_999_999)


class ReverseSaleRequest(BaseModel):
    """POST /api/v1/pos/sale/{receipt_no}/reverse"""

    model_config = ConfigDict(extra="forbid")

    return_receipt_no: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    reason: str | None = Field(default=None, max_length=500)


#
# Response models
#


class CustomerSummary(BaseModel):
    """Customer fields returned by lookup. Email/phone/customer_qr are NOT included
    by Paylo for POS surface — the rotating QR system exists so the static QR
    never leaves the customer device."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str


class BucketSummary(BaseModel):
    """Per-merchant bucket snapshot returned by lookup."""

    model_config = ConfigDict(extra="forbid")

    balance: int
    earned_total: int
    redeemed_total: int


class LookupCustomerResponse(BaseModel):
    """Both ``ok`` and ``not_found`` use this shape — only ``status`` differs.

    Enumeration protection: HTTP 200 in both cases, structure is identical, the
    only signal is the ``status`` field. POSNET must not branch on HTTP status.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "not_found"]
    customer: CustomerSummary | None
    bucket: BucketSummary | None


class PreviewSaleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sale_amount: int
    earn_amount: int
    redeem_amount: int
    final_to_pay: int
    projected_balance: int


class CompleteSaleResponse(BaseModel):
    """``idempotent=true`` means the server returned a previously-recorded
    transaction (either via Idempotency-Key cache or domain-level receipt_no
    constraint). The client should treat ``idempotent=true`` as success."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: int
    receipt_no: str
    status: Literal["completed", "reversed", "refunded"]
    idempotent: bool


class ReverseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str
    type: str
    amount: int


class ReverseSaleResponse(BaseModel):
    """Successful reverse response. ``already_reversed=true`` for idempotent retry."""

    model_config = ConfigDict(extra="allow")  # http_status excluded server-side; future fields ok

    transaction_id: int | None = None
    receipt_no: str | None = None
    status: Literal["reversed", "not_found"]
    already_reversed: bool = False
    reverse_entries: list[ReverseEntry] = Field(default_factory=list)
    message: str | None = None


class TransactionRecord(BaseModel):
    """One row of the reconciliation feed."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: int
    receipt_no: str
    branch_id: int | None
    customer_id: int
    cashier_id: int
    sale_amount: int
    earned_amount: int
    redeemed_amount: int
    status: Literal["completed", "reversed", "refunded"]
    occurred_at: datetime
    created_at: datetime


class TransactionsPage(BaseModel):
    """Cursor-paginated reconciliation feed response."""

    model_config = ConfigDict(extra="forbid")

    data: list[TransactionRecord]
    next_cursor: str | None
    has_more: bool


class TransactionsFeedQuery(BaseModel):
    """Optional filter+pagination for ``transactions(...)``. The client builds
    query strings from this — None values are dropped."""

    model_config = ConfigDict(extra="forbid")

    cursor: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    status: Literal["completed", "reversed", "refunded"] | None = None
    limit: int | None = Field(default=None, ge=1, le=200)
