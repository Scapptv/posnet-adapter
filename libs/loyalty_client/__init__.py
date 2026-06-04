"""Paylo loyalty API client for POSNET integration.

Public usage:

    from libs.loyalty_client import (
        LoyaltyClient,
        CompleteSaleRequest,
        LookupCustomerResponse,
        LoyaltyInsufficientFundsError,
    )

    async with LoyaltyClient(base_url=..., token=...) as client:
        result = await client.complete_sale(CompleteSaleRequest(
            customer_id=8,
            sale_amount_cents=5000,
            receipt_no="POS01-2026-06-04-00042",
            use_bonus=False,
        ))
        log.info("sale.committed", tx_id=result.transaction_id, idempotent=result.idempotent)
"""

from __future__ import annotations

from .client import LoyaltyClient
from .errors import (
    LoyaltyAbilityError,
    LoyaltyAuthError,
    LoyaltyError,
    LoyaltyIdempotencyConflictError,
    LoyaltyInsufficientFundsError,
    LoyaltyNetworkError,
    LoyaltyNotFoundError,
    LoyaltyRateLimitedError,
    LoyaltyServerError,
    LoyaltyValidationError,
)
from .idempotency import new_idempotency_key
from .models import (
    BucketSummary,
    CompleteSaleRequest,
    CompleteSaleResponse,
    CustomerSummary,
    LookupCustomerRequest,
    LookupCustomerResponse,
    PreviewSaleRequest,
    PreviewSaleResponse,
    ReverseEntry,
    ReverseSaleRequest,
    ReverseSaleResponse,
    TransactionRecord,
    TransactionsFeedQuery,
    TransactionsPage,
)
from .reconcile import DriftCategory, DriftEntry, LocalLookup, ReconciliationReport, reconcile
from .vault_loader import (
    client_from_vault,
    client_from_vault_with_auto_rotation,
    hmac_secret_ref_for,
    load_hmac_secret,
    load_token,
    rotate_client,
    token_ref_for,
)
from .webhooks import (
    AdminReverseEvent,
    BucketExpireEvent,
    WebhookEvent,
    WebhookEventError,
    WebhookVerificationError,
    WebhookVerifier,
)

__all__ = [
    "AdminReverseEvent",
    "BucketExpireEvent",
    "BucketSummary",
    "CompleteSaleRequest",
    "CompleteSaleResponse",
    "CustomerSummary",
    "DriftCategory",
    "DriftEntry",
    "LocalLookup",
    "LookupCustomerRequest",
    "LookupCustomerResponse",
    "LoyaltyAbilityError",
    "LoyaltyAuthError",
    "LoyaltyClient",
    "LoyaltyError",
    "LoyaltyIdempotencyConflictError",
    "LoyaltyInsufficientFundsError",
    "LoyaltyNetworkError",
    "LoyaltyNotFoundError",
    "LoyaltyRateLimitedError",
    "LoyaltyServerError",
    "LoyaltyValidationError",
    "PreviewSaleRequest",
    "PreviewSaleResponse",
    "ReconciliationReport",
    "ReverseEntry",
    "ReverseSaleRequest",
    "ReverseSaleResponse",
    "TransactionRecord",
    "TransactionsFeedQuery",
    "TransactionsPage",
    "WebhookEvent",
    "WebhookEventError",
    "WebhookVerificationError",
    "WebhookVerifier",
    "client_from_vault",
    "client_from_vault_with_auto_rotation",
    "hmac_secret_ref_for",
    "load_hmac_secret",
    "load_token",
    "new_idempotency_key",
    "reconcile",
    "rotate_client",
    "token_ref_for",
]
