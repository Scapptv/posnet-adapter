"""Drift-tracking reconciliation between POSNET local state and Paylo's ledger.

Why this exists
---------------
Paylo's POS API is idempotent at two layers (Idempotency-Key cache + domain
``(merchant_id, receipt_no)`` unique constraint), but neither layer covers the
case where:

  * POSNET committed locally that a sale was sent and acked, but the ack was
    lost; the cache expired; now POSNET cannot prove the sale landed.
  * An admin reversed a Paylo transaction via the admin console — POSNET has
    no event to learn this happened.
  * A bug in POSNET's outbound code recorded a sale as "committed" while the
    HTTP request never actually reached Paylo.

The reconciliation pass pulls Paylo's view of "all transactions since T" and
diffs it against POSNET's local view. Drift is categorised so the caller can
decide which class to ignore (LOCAL_MISSING in the seconds after a sale is
benign — eventual consistency) and which to alert on (STATUS_MISMATCH on a
mature receipt is a real divergence).

Decoupling
----------
This module owns the diff *protocol*, not POSNET's local schema. Callers pass
an async ``local_lookup`` callback that returns the local status string (or
``None`` for "unknown locally"). The implementation can hit Postgres, an
in-memory cache, anything — we only require that the call returns within the
batch budget.

Scheduling
----------
Not our concern. Wire the ``reconcile`` coroutine into your existing scheduler
(APScheduler, Celery beat, cron + uvicorn one-shot). A reasonable default is
hourly with ``since=now - 2h`` (overlap protects against clock skew).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from .models import TransactionRecord, TransactionsFeedQuery

if TYPE_CHECKING:
    from .client import LoyaltyClient

LocalLookup = Callable[[str], Awaitable[str | None]]
"""Async callback ``(receipt_no) -> local_status | None``.

The status string SHOULD match Paylo's enum (``completed``, ``reversed``,
``refunded``) so :class:`DriftCategory.STATUS_MISMATCH` fires only on real
divergence. ``None`` means "this receipt is unknown to POSNET".
"""


class DriftCategory(StrEnum):
    """How POSNET's view of a transaction differs from Paylo's."""

    LOCAL_MISSING = "local_missing"
    """Paylo has the tx; POSNET does not. Either (a) POSNET lost the response of a
    sale it actually sent, or (b) the tx was never POSNET-initiated (manual
    Paylo admin entry, rare). Action: investigate; for case (a), reconcile by
    inserting a local row marked ``synced``."""

    STATUS_MISMATCH = "status_mismatch"
    """Both sides have the receipt, but the status string differs. Most common
    cause: an admin reversed the sale via Paylo's admin console after POSNET
    had already locked the local row as ``completed``. Action: update the
    local row to match Paylo's status and emit a notification."""


@dataclass(frozen=True)
class DriftEntry:
    """One discrepancy between Paylo and POSNET for a specific receipt."""

    category: DriftCategory
    receipt_no: str
    paylo_status: str
    local_status: str | None
    paylo_transaction_id: int
    paylo_occurred_at: datetime


@dataclass
class ReconciliationReport:
    """Outcome of a reconciliation pass.

    ``matched`` is the count of transactions where Paylo and POSNET agree.
    ``drift`` is the per-receipt list of disagreements, in the order they were
    encountered (which is Paylo's ``occurred_at DESC`` newest-first). Callers
    typically log ``drift`` and emit ``len(drift)`` to a gauge so an alert
    fires when the number stays non-zero across consecutive passes (one-pass
    drift is often just timing).
    """

    matched: int = 0
    drift: list[DriftEntry] = field(default_factory=list)
    pages_pulled: int = 0
    total_paylo_records: int = 0

    def count(self, category: DriftCategory) -> int:
        """Number of drift entries of a given category — for metric labels."""
        return sum(1 for d in self.drift if d.category == category)

    @property
    def is_clean(self) -> bool:
        """True when every Paylo record matched a local row with the same status."""
        return self.drift == []


async def reconcile(
    client: LoyaltyClient,
    *,
    local_lookup: LocalLookup,
    since: datetime | None = None,
    until: datetime | None = None,
    page_size: int = 200,
    max_pages: int = 50,
) -> ReconciliationReport:
    """Pull Paylo's transactions feed and classify drift against POSNET local state.

    Parameters
    ----------
    client:
        Authenticated :class:`LoyaltyClient`. Reuse a per-merchant client —
        Paylo's transactions feed is merchant-scoped by token.
    local_lookup:
        Async callback returning POSNET's local status for a receipt, or
        ``None`` if the receipt is unknown locally.
    since, until:
        ``occurred_at`` window on Paylo's side. ``since`` is typically the
        previous successful pass's ``until`` minus an overlap margin (e.g.
        15 min) to absorb clock skew. ``None`` means no bound.
    page_size:
        Per-request limit; 1..200 honoured by Paylo. Default 200 minimises
        round-trips for the common "hourly batch" use case.
    max_pages:
        Safety cap so a misconfigured large window doesn't hang us. Reaching
        the cap surfaces in the report's ``pages_pulled`` for the caller to
        compare against ``max_pages``.

    Returns
    -------
    ReconciliationReport
        ``matched`` + per-receipt ``drift`` list. The function does NOT mutate
        local state; remediation is the caller's call.
    """
    report = ReconciliationReport()
    cursor: str | None = None

    while report.pages_pulled < max_pages:
        page = await client.transactions(
            TransactionsFeedQuery(cursor=cursor, since=since, until=until, limit=page_size)
        )
        report.pages_pulled += 1
        report.total_paylo_records += len(page.data)

        for tx in page.data:
            await _classify(tx, local_lookup, report)

        if not page.has_more or page.next_cursor is None:
            break
        cursor = page.next_cursor

    return report


async def _classify(
    tx: TransactionRecord,
    local_lookup: LocalLookup,
    report: ReconciliationReport,
) -> None:
    """Compare one Paylo record against POSNET's view, mutate the report."""
    local_status = await local_lookup(tx.receipt_no)

    if local_status is None:
        report.drift.append(
            DriftEntry(
                category=DriftCategory.LOCAL_MISSING,
                receipt_no=tx.receipt_no,
                paylo_status=tx.status,
                local_status=None,
                paylo_transaction_id=tx.transaction_id,
                paylo_occurred_at=tx.occurred_at,
            )
        )
        return

    if local_status != tx.status:
        report.drift.append(
            DriftEntry(
                category=DriftCategory.STATUS_MISMATCH,
                receipt_no=tx.receipt_no,
                paylo_status=tx.status,
                local_status=local_status,
                paylo_transaction_id=tx.transaction_id,
                paylo_occurred_at=tx.occurred_at,
            )
        )
        return

    report.matched += 1
