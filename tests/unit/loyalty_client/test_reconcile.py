"""Unit tests for the drift-tracking reconciliation pass.

Paylo's transactions feed is mocked via respx; the local lookup is an
in-memory dict so the test owns the "POSNET local state" deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from libs.loyalty_client import (
    DriftCategory,
    LoyaltyClient,
    reconcile,
)

BASE = "https://paylo.test"
TOKEN = "tok_reconcile_aaaabbbbcccc"


def _record(receipt_no: str, status: str = "completed", tx_id: int = 1) -> dict[str, object]:
    """Build one Paylo TransactionRecord-shaped dict (Paylo's response body)."""
    return {
        "transaction_id": tx_id,
        "receipt_no": receipt_no,
        "branch_id": None,
        "customer_id": 8,
        "cashier_id": 16,
        "sale_amount": 5000,
        "earned_amount": 100,
        "redeemed_amount": 0,
        "status": status,
        "occurred_at": "2026-06-04T12:00:00+04:00",
        "created_at": "2026-06-04T12:00:00+04:00",
    }


def _client() -> LoyaltyClient:
    return LoyaltyClient(base_url=BASE, token=TOKEN, max_retries=1)


@pytest.mark.unit
@respx.mock
async def test_perfect_sync_returns_zero_drift() -> None:
    """When every Paylo record has a matching local record with identical status,
    ``is_clean`` is True and ``matched`` is the full record count."""
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_record("r-1", tx_id=1), _record("r-2", tx_id=2)],
                "next_cursor": None,
                "has_more": False,
            },
        )
    )

    local = {"r-1": "completed", "r-2": "completed"}

    async def lookup(receipt_no: str) -> str | None:
        return local.get(receipt_no)

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup)

    assert report.is_clean is True
    assert report.matched == 2
    assert report.drift == []
    assert report.total_paylo_records == 2
    assert report.pages_pulled == 1


@pytest.mark.unit
@respx.mock
async def test_local_missing_is_reported() -> None:
    """Paylo has a tx that POSNET has never seen — classic 'lost response' case
    after a sale was committed server-side but the ack failed in transit."""
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_record("r-known", tx_id=1), _record("r-orphan", tx_id=2)],
                "next_cursor": None,
                "has_more": False,
            },
        )
    )

    local = {"r-known": "completed"}

    async def lookup(receipt_no: str) -> str | None:
        return local.get(receipt_no)

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup)

    assert report.matched == 1
    assert report.count(DriftCategory.LOCAL_MISSING) == 1
    drift = report.drift[0]
    assert drift.receipt_no == "r-orphan"
    assert drift.local_status is None
    assert drift.paylo_status == "completed"


@pytest.mark.unit
@respx.mock
async def test_status_mismatch_is_reported() -> None:
    """POSNET still says 'completed' but an admin reversed the sale in Paylo —
    this is the case for which the cron is most operationally important."""
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_record("r-rev", status="reversed", tx_id=99)],
                "next_cursor": None,
                "has_more": False,
            },
        )
    )

    local = {"r-rev": "completed"}

    async def lookup(receipt_no: str) -> str | None:
        return local.get(receipt_no)

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup)

    assert report.matched == 0
    assert report.count(DriftCategory.STATUS_MISMATCH) == 1
    drift = report.drift[0]
    assert drift.local_status == "completed"
    assert drift.paylo_status == "reversed"
    assert drift.paylo_transaction_id == 99


@pytest.mark.unit
@respx.mock
async def test_pagination_traverses_all_pages() -> None:
    """A single ``transactions()`` page rarely fits a full reconciliation
    window. The pass MUST follow cursors until ``has_more=false``."""
    route = respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": [_record("p1-a", tx_id=1), _record("p1-b", tx_id=2)],
                    "next_cursor": "page-2-cursor",
                    "has_more": True,
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [_record("p2-a", tx_id=3)],
                    "next_cursor": None,
                    "has_more": False,
                },
            ),
        ]
    )

    local = {"p1-a": "completed", "p1-b": "completed", "p2-a": "completed"}

    async def lookup(receipt_no: str) -> str | None:
        return local.get(receipt_no)

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup)

    assert report.pages_pulled == 2
    assert report.total_paylo_records == 3
    assert report.matched == 3
    # The second call's cursor must be the one returned by the first page.
    assert route.calls[1].request.url.params["cursor"] == "page-2-cursor"


@pytest.mark.unit
@respx.mock
async def test_max_pages_caps_runaway_window() -> None:
    """Belt-and-suspenders: a misconfigured ``since`` could nominate millions of
    rows. ``max_pages`` stops the loop and surfaces partial results."""
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_record("infinite", tx_id=1)],
                "next_cursor": "always-more",
                "has_more": True,
            },
        )
    )

    async def lookup(receipt_no: str) -> str | None:
        return "completed"

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup, max_pages=3)

    assert report.pages_pulled == 3
    assert report.matched == 3
    # Caller can see this is a capped run by comparing pages_pulled to max_pages.


@pytest.mark.unit
@respx.mock
async def test_since_until_query_params_pass_through() -> None:
    """The reconciler must forward ``since`` / ``until`` to Paylo so the server
    can prune the result set; doing the filtering in-Python would defeat the
    point of the feed."""
    route = respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(200, json={"data": [], "next_cursor": None, "has_more": False})
    )

    since = datetime(2026, 6, 4, 0, 0, 0, tzinfo=UTC)
    until = datetime(2026, 6, 4, 23, 59, 59, tzinfo=UTC)

    async def lookup(receipt_no: str) -> str | None:
        return None  # unused — no records

    async with _client() as c:
        await reconcile(c, local_lookup=lookup, since=since, until=until)

    params = route.calls.last.request.url.params
    assert "since" in params
    assert "until" in params


@pytest.mark.unit
@respx.mock
async def test_empty_feed_returns_clean_report() -> None:
    """A reconciliation window with zero Paylo activity is the happy case."""
    respx.get(f"{BASE}/api/v1/pos/transactions").mock(
        return_value=httpx.Response(200, json={"data": [], "next_cursor": None, "has_more": False})
    )

    async def lookup(receipt_no: str) -> str | None:
        return None  # unused

    async with _client() as c:
        report = await reconcile(c, local_lookup=lookup)

    assert report.is_clean is True
    assert report.matched == 0
    assert report.total_paylo_records == 0
