"""Boundary tests for the Pydantic v2 request models — Paylo's regex/range
constraints must be enforced client-side too so we fail fast before sending
a 422-guaranteed request over the wire."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.loyalty_client import (
    CompleteSaleRequest,
    LookupCustomerRequest,
    PreviewSaleRequest,
    ReverseSaleRequest,
)


@pytest.mark.unit
def test_complete_sale_rejects_receipt_no_with_spaces() -> None:
    with pytest.raises(ValidationError):
        CompleteSaleRequest(
            customer_id=8, sale_amount_cents=5000, receipt_no="has spaces", use_bonus=False
        )


@pytest.mark.unit
def test_complete_sale_accepts_alphanumeric_dash_underscore() -> None:
    req = CompleteSaleRequest(
        customer_id=8, sale_amount_cents=5000, receipt_no="POS01_2026-06-04", use_bonus=False
    )
    assert req.receipt_no == "POS01_2026-06-04"


@pytest.mark.unit
def test_complete_sale_rejects_zero_sale_amount() -> None:
    with pytest.raises(ValidationError):
        CompleteSaleRequest(customer_id=8, sale_amount_cents=0, receipt_no="r-1", use_bonus=False)


@pytest.mark.unit
def test_complete_sale_rejects_overflow_sale_amount() -> None:
    with pytest.raises(ValidationError):
        CompleteSaleRequest(
            customer_id=8, sale_amount_cents=100_000_000, receipt_no="r-1", use_bonus=False
        )


@pytest.mark.unit
def test_lookup_rejects_overly_long_qr() -> None:
    with pytest.raises(ValidationError):
        LookupCustomerRequest(qr="x" * 193)


@pytest.mark.unit
def test_reverse_rejects_spaces_in_return_receipt() -> None:
    with pytest.raises(ValidationError):
        ReverseSaleRequest(return_receipt_no="RET 001")


@pytest.mark.unit
def test_reverse_rejects_oversized_reason() -> None:
    with pytest.raises(ValidationError):
        ReverseSaleRequest(return_receipt_no="RET-001", reason="x" * 501)


@pytest.mark.unit
def test_preview_extra_fields_rejected_by_strict_config() -> None:
    """``extra='forbid'`` catches client-side typos like ``sale_amount`` (legacy
    float field name) before we waste a request on a guaranteed 422."""
    with pytest.raises(ValidationError):
        PreviewSaleRequest.model_validate(
            {
                "customer_id": 8,
                "sale_amount_cents": 5000,
                "use_bonus": False,
                "sale_amount": 50.00,  # legacy float field
            }
        )
