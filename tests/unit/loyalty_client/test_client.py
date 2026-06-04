"""Unit tests for the async :class:`LoyaltyClient`.

Network is mocked via :mod:`respx`. Each test wires one or more Paylo response
shapes and verifies (a) the client maps the response to the right typed model
or exception, (b) the right HTTP shape goes out (URL, headers, body).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from libs.loyalty_client import (
    CompleteSaleRequest,
    LoyaltyAbilityError,
    LoyaltyAuthError,
    LoyaltyClient,
    LoyaltyIdempotencyConflictError,
    LoyaltyInsufficientFundsError,
    LoyaltyNetworkError,
    LoyaltyNotFoundError,
    LoyaltyRateLimitedError,
    LoyaltyServerError,
    LoyaltyValidationError,
    PreviewSaleRequest,
    ReverseSaleRequest,
    TransactionsFeedQuery,
)

BASE = "https://paylo.test"
TOKEN = "tok_smoke_aaaabbbbccccddddeeeeffff"


def _client() -> LoyaltyClient:
    """Construct a client with retries disabled — tests for the retry loop
    explicitly enable it; everywhere else we want failure to surface immediately."""
    return LoyaltyClient(base_url=BASE, token=TOKEN, max_retries=1)


@pytest.mark.unit
@respx.mock
async def test_lookup_customer_ok() -> None:
    respx.post(f"{BASE}/api/v1/pos/customer/lookup").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "customer": {"id": 8, "name": "Aysel"},
                "bucket": {"balance": 0, "earned_total": 0, "redeemed_total": 0},
            },
        )
    )

    async with _client() as c:
        r = await c.lookup_customer(qr="qr_real")

    assert r.status == "ok"
    assert r.customer is not None and r.customer.id == 8
    assert r.bucket is not None and r.bucket.balance == 0


@pytest.mark.unit
@respx.mock
async def test_lookup_customer_not_found_is_ok_with_status_field() -> None:
    """Paylo returns HTTP 200 even for unknown QRs (enumeration protection).
    The client must NOT branch on HTTP status — only on the response.status field."""
    respx.post(f"{BASE}/api/v1/pos/customer/lookup").mock(
        return_value=httpx.Response(
            200, json={"status": "not_found", "customer": None, "bucket": None}
        )
    )

    async with _client() as c:
        r = await c.lookup_customer(qr="qr_doesnotexist")

    assert r.status == "not_found"
    assert r.customer is None and r.bucket is None


@pytest.mark.unit
@respx.mock
async def test_preview_sale_decodes_response_shape() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(
            200,
            json={
                "sale_amount": 5000,
                "earn_amount": 100,
                "redeem_amount": 0,
                "final_to_pay": 5000,
                "projected_balance": 100,
            },
        )
    )

    async with _client() as c:
        r = await c.preview_sale(
            PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
        )

    assert r.earn_amount == 100
    assert r.final_to_pay == 5000


@pytest.mark.unit
@respx.mock
async def test_complete_sale_auto_generates_idempotency_key() -> None:
    """When the caller omits ``idempotency_key``, the client must mint a fresh ULID
    and send it as ``Idempotency-Key``. Paylo's middleware accepts 8-128 char keys."""
    route = respx.post(f"{BASE}/api/v1/pos/sale").mock(
        return_value=httpx.Response(
            200,
            json={
                "transaction_id": 147,
                "receipt_no": "r-1",
                "status": "completed",
                "idempotent": False,
            },
        )
    )

    async with _client() as c:
        await c.complete_sale(
            CompleteSaleRequest(
                customer_id=8, sale_amount_cents=5000, receipt_no="r-1", use_bonus=False
            )
        )

    sent = route.calls.last.request
    sent_key = sent.headers.get("idempotency-key")
    assert sent_key is not None
    assert 8 <= len(sent_key) <= 128


@pytest.mark.unit
@respx.mock
async def test_complete_sale_preserves_explicit_idempotency_key() -> None:
    """When the caller IS recovering from a lost response, it must be able to
    pass the original key — otherwise Paylo's cache-replay can't fire."""
    fixed_key = "01HX7K3R4M5N6P7Q8R9S"
    route = respx.post(f"{BASE}/api/v1/pos/sale").mock(
        return_value=httpx.Response(
            200,
            json={
                "transaction_id": 147,
                "receipt_no": "r-1",
                "status": "completed",
                "idempotent": True,
            },
        )
    )

    async with _client() as c:
        r = await c.complete_sale(
            CompleteSaleRequest(
                customer_id=8, sale_amount_cents=5000, receipt_no="r-1", use_bonus=False
            ),
            idempotency_key=fixed_key,
        )

    assert route.calls.last.request.headers["idempotency-key"] == fixed_key
    assert r.idempotent is True


@pytest.mark.unit
@respx.mock
async def test_401_maps_to_auth_error() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated."})
    )
    async with _client() as c:
        with pytest.raises(LoyaltyAuthError) as exc_info:
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    assert exc_info.value.status == 401


@pytest.mark.unit
@respx.mock
async def test_403_maps_to_ability_error() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(403, json={"message": "Invalid ability."})
    )
    async with _client() as c:
        with pytest.raises(LoyaltyAbilityError):
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )


@pytest.mark.unit
@respx.mock
async def test_422_field_errors_map_to_validation_error() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale").mock(
        return_value=httpx.Response(
            422,
            json={
                "message": "The given data was invalid.",
                "errors": {"customer_id": ["The customer id field is required."]},
            },
        )
    )
    async with _client() as c:
        with pytest.raises(LoyaltyValidationError) as exc_info:
            await c.complete_sale(
                CompleteSaleRequest(
                    customer_id=999, sale_amount_cents=5000, receipt_no="r-1", use_bonus=False
                )
            )
    assert "customer_id" in exc_info.value.field_errors


@pytest.mark.unit
@respx.mock
async def test_idempotency_key_body_conflict_maps_to_dedicated_error() -> None:
    """422 with ``errors.Idempotency-Key`` is distinct from a generic validation
    error — it signals client state corruption (same key, different body)."""
    respx.post(f"{BASE}/api/v1/pos/sale").mock(
        return_value=httpx.Response(
            422,
            json={
                "message": "Idempotency-Key reused with different body.",
                "errors": {"Idempotency-Key": ["Key reused with different body."]},
            },
        )
    )
    async with _client() as c:
        with pytest.raises(LoyaltyIdempotencyConflictError):
            await c.complete_sale(
                CompleteSaleRequest(
                    customer_id=8, sale_amount_cents=5000, receipt_no="r-x", use_bonus=False
                )
            )


@pytest.mark.unit
@respx.mock
async def test_insufficient_funds_carries_machine_readable_amounts() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale").mock(
        return_value=httpx.Response(
            422,
            json={
                "status": "insufficient_funds",
                "message": "Insufficient funds",
                "available_cents": 50,
                "required_cents": 100,
            },
        )
    )
    async with _client() as c:
        with pytest.raises(LoyaltyInsufficientFundsError) as exc_info:
            await c.complete_sale(
                CompleteSaleRequest(
                    customer_id=8,
                    sale_amount_cents=5000,
                    receipt_no="r-broke",
                    use_bonus=True,
                    redeem_cents=100,
                )
            )
    assert exc_info.value.available_cents == 50
    assert exc_info.value.required_cents == 100


@pytest.mark.unit
@respx.mock
async def test_429_maps_to_rate_limited_with_retry_after() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(
            429, json={"message": "Too many attempts."}, headers={"Retry-After": "12"}
        )
    )
    async with _client() as c:
        with pytest.raises(LoyaltyRateLimitedError) as exc_info:
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    assert exc_info.value.retry_after_seconds == 12


@pytest.mark.unit
@respx.mock
async def test_500_maps_to_server_error() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(500, json={"message": "Server error"})
    )
    async with _client() as c:
        with pytest.raises(LoyaltyServerError):
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )


@pytest.mark.unit
@respx.mock
async def test_404_on_reverse_maps_to_not_found() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/foreign-rcpt/reverse").mock(
        return_value=httpx.Response(
            404, json={"status": "not_found", "message": "Receipt not found"}
        )
    )
    async with _client() as c:
        with pytest.raises(LoyaltyNotFoundError):
            await c.reverse_sale("foreign-rcpt", ReverseSaleRequest(return_receipt_no="RET-1"))


@pytest.mark.unit
@respx.mock
async def test_network_failure_maps_to_network_error() -> None:
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(side_effect=httpx.ConnectError("boom"))
    async with _client() as c:
        with pytest.raises(LoyaltyNetworkError):
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )


@pytest.mark.unit
@respx.mock
async def test_retries_on_500_and_eventually_succeeds() -> None:
    """When retries are enabled (default = 4 attempts), transient 500s must be
    retried and only fail when ALL attempts fail. One success after a 500
    must surface as a success."""
    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        side_effect=[
            httpx.Response(500, json={"message": "transient"}),
            httpx.Response(
                200,
                json={
                    "sale_amount": 5000,
                    "earn_amount": 100,
                    "redeem_amount": 0,
                    "final_to_pay": 5000,
                    "projected_balance": 100,
                },
            ),
        ]
    )

    async with LoyaltyClient(base_url=BASE, token=TOKEN, max_retries=3) as c:
        r = await c.preview_sale(
            PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
        )

    assert r.earn_amount == 100


@pytest.mark.unit
@respx.mock
async def test_does_not_retry_on_422_validation_error() -> None:
    """Validation errors are deterministic — retrying just burns the rate-limit
    budget. The client must give up after the first 422."""
    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(422, json={"message": "bad", "errors": {"x": ["y"]}})
    )

    async with LoyaltyClient(base_url=BASE, token=TOKEN, max_retries=5) as c:
        with pytest.raises(LoyaltyValidationError):
            await c.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )

    assert route.call_count == 1


@pytest.mark.unit
@respx.mock
async def test_transactions_feed_encodes_query_params() -> None:
    route = respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(200, json={"data": [], "next_cursor": None, "has_more": False})
    )

    async with _client() as c:
        await c.transactions(TransactionsFeedQuery(limit=50, status="completed"))

    assert route.calls.last.request.url.params["limit"] == "50"
    assert route.calls.last.request.url.params["status"] == "completed"


@pytest.mark.unit
@respx.mock
async def test_transactions_feed_decodes_page() -> None:
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "transaction_id": 147,
                        "receipt_no": "POS01-002",
                        "branch_id": None,
                        "customer_id": 8,
                        "cashier_id": 16,
                        "sale_amount": 10000,
                        "earned_amount": 250,
                        "redeemed_amount": 50,
                        "status": "completed",
                        "occurred_at": "2026-06-04T02:59:50+04:00",
                        "created_at": "2026-06-04T02:59:50+04:00",
                    }
                ],
                "next_cursor": "cur-abc",
                "has_more": True,
            },
        )
    )

    async with _client() as c:
        page = await c.transactions(TransactionsFeedQuery(limit=1))

    assert page.has_more is True
    assert page.next_cursor == "cur-abc"
    assert len(page.data) == 1
    assert page.data[0].receipt_no == "POS01-002"
    assert page.data[0].earned_amount == 250


@pytest.mark.unit
@respx.mock
async def test_sends_authorization_header_on_every_call() -> None:
    """The bearer token must be on every request — never optional, never
    accidentally lost in a header merge."""
    route = respx.post(f"{BASE}/api/v1/pos/customer/lookup").mock(
        return_value=httpx.Response(
            200, json={"status": "not_found", "customer": None, "bucket": None}
        )
    )

    async with _client() as c:
        await c.lookup_customer(qr="qr_x")

    assert route.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"
