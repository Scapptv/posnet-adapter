"""Live end-to-end smoke against a local Paylo dev server.

Run while ``php -S 127.0.0.1:8000 -t public server.php`` is up and a valid
``pos:write`` token is exported. This script is not part of the pytest run —
it exists so the integration is observably real before we commit.

Usage::

    set PAYLO_BASE=http://127.0.0.1:8000
    set PAYLO_TOKEN=5|<token>
    .venv\\Scripts\\python.exe scripts\\smoke_loyalty_client.py qr_6tgkgwdzyprz 8
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from libs.loyalty_client import (
    CompleteSaleRequest,
    LoyaltyClient,
    LoyaltyInsufficientFundsError,
    PreviewSaleRequest,
    ReverseSaleRequest,
    TransactionsFeedQuery,
)


async def main(qr: str, customer_id: int) -> None:
    base = os.environ.get("PAYLO_BASE", "http://127.0.0.1:8000")
    token = os.environ.get("PAYLO_TOKEN")
    if not token:
        sys.stderr.write("PAYLO_TOKEN is required (issue with: php artisan pos:issue-token)\n")
        raise SystemExit(2)

    async with LoyaltyClient(base_url=base, token=token) as client:
        # 1. Look up customer
        lookup = await client.lookup_customer(qr=qr)
        sys.stdout.write(f"lookup status={lookup.status}\n")
        if lookup.customer:
            sys.stdout.write(f"  customer.id={lookup.customer.id} name={lookup.customer.name}\n")
        if lookup.bucket:
            sys.stdout.write(f"  bucket.balance={lookup.bucket.balance}\n")

        # 2. Preview a 50 AZN sale
        preview = await client.preview_sale(
            PreviewSaleRequest(customer_id=customer_id, sale_amount_cents=5000, use_bonus=False)
        )
        sys.stdout.write(
            f"preview sale={preview.sale_amount} earn={preview.earn_amount} "
            f"final={preview.final_to_pay}\n"
        )

        # 3. Complete a sale (auto-generated Idempotency-Key)
        receipt = f"py-smoke-{int(time.time())}"
        sale = await client.complete_sale(
            CompleteSaleRequest(
                customer_id=customer_id,
                sale_amount_cents=5000,
                receipt_no=receipt,
                use_bonus=False,
            )
        )
        sys.stdout.write(
            f"sale tx_id={sale.transaction_id} receipt={sale.receipt_no} "
            f"status={sale.status} idempotent={sale.idempotent}\n"
        )

        # 4. Reverse it
        reverse = await client.reverse_sale(
            receipt,
            ReverseSaleRequest(return_receipt_no=f"RET-{receipt}", reason="smoke test"),
        )
        sys.stdout.write(
            f"reverse status={reverse.status} already={reverse.already_reversed} "
            f"entries={len(reverse.reverse_entries)}\n"
        )

        # 5. Reconciliation feed — fetch the latest 5 tx for this merchant
        feed = await client.transactions(TransactionsFeedQuery(limit=5))
        sys.stdout.write(f"feed count={len(feed.data)} has_more={feed.has_more}\n")
        for tx in feed.data:
            sys.stdout.write(
                f"  - tx={tx.transaction_id} receipt={tx.receipt_no} "
                f"status={tx.status} occurred_at={tx.occurred_at.isoformat()}\n"
            )

        # 6. Demonstrate typed exception on a deliberately broken sale
        try:
            await client.complete_sale(
                CompleteSaleRequest(
                    customer_id=customer_id,
                    sale_amount_cents=5000,
                    receipt_no=f"py-broke-{int(time.time())}",
                    use_bonus=True,
                    redeem_cents=999_999,
                )
            )
        except LoyaltyInsufficientFundsError as exc:
            sys.stdout.write(
                f"insufficient_funds caught available={exc.available_cents} "
                f"required={exc.required_cents}\n"
            )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write("usage: smoke_loyalty_client.py <customer_qr> <customer_id>\n")
        raise SystemExit(2)
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
