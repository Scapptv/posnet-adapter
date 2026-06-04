"""Typed exception hierarchy for the Paylo loyalty client.

Each exception carries enough context for the caller to decide whether to retry,
surface the error to the operator, or fail the sale workflow.

Mapping from Paylo HTTP responses:
    - 401                  → LoyaltyAuthError       (token invalid / expired)
    - 403                  → LoyaltyAbilityError    (token lacks `pos:write`)
    - 404                  → LoyaltyNotFoundError   (receipt/customer scope miss)
    - 422 (validation)     → LoyaltyValidationError (client bug — DO NOT retry)
    - 422 (idem conflict)  → LoyaltyIdempotencyConflictError (key reuse with diff body)
    - 422 (insufficient)   → LoyaltyInsufficientFundsError (bucket underflow on redeem)
    - 429                  → LoyaltyRateLimitedError     (retry after `retry_after_seconds`)
    - 5xx                  → LoyaltyServerError     (transient — safe to retry)
    - network / timeout    → LoyaltyNetworkError    (transient — safe to retry)
"""

from __future__ import annotations

from typing import Any


class LoyaltyError(Exception):
    """Base loyalty client exception. All raised errors inherit this."""

    def __init__(
        self,
        detail: str,
        *,
        status: int | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.body = body or {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status!r}, detail={self.detail!r})"


class LoyaltyAuthError(LoyaltyError):
    """Sanctum token is invalid, expired or revoked. Operator must rotate token."""


class LoyaltyAbilityError(LoyaltyError):
    """Token does not carry `pos:write` ability. Re-issue with correct ability."""


class LoyaltyNotFoundError(LoyaltyError):
    """Receipt or resource not found. For reverse: receipt may belong to another merchant."""


class LoyaltyValidationError(LoyaltyError):
    """Paylo rejected the request body. Client bug — DO NOT retry without fixing."""

    def __init__(
        self,
        detail: str,
        *,
        status: int | None = 422,
        body: dict[str, Any] | None = None,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(detail, status=status, body=body)
        self.field_errors = field_errors or {}


class LoyaltyIdempotencyConflictError(LoyaltyError):
    """Same Idempotency-Key reused with a different body. Client state bug."""


class LoyaltyInsufficientFundsError(LoyaltyError):
    """Customer bucket balance does not cover the requested redeem amount."""

    def __init__(
        self,
        detail: str,
        *,
        available_cents: int,
        required_cents: int,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail, status=422, body=body)
        self.available_cents = available_cents
        self.required_cents = required_cents


class LoyaltyRateLimitedError(LoyaltyError):
    """Per-token throttle exceeded. Honour `retry_after_seconds` before retrying."""

    def __init__(
        self,
        detail: str,
        *,
        retry_after_seconds: int,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail, status=429, body=body)
        self.retry_after_seconds = retry_after_seconds


class LoyaltyServerError(LoyaltyError):
    """Paylo returned 5xx. Transient — safe to retry with backoff."""


class LoyaltyNetworkError(LoyaltyError):
    """Transport-layer failure (DNS, TCP, TLS, timeout). Safe to retry with backoff."""
