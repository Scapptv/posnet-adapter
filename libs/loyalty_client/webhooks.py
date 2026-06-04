"""Inbound webhook verification for POSNET's loyalty event receiver.

Paylo posts events to a URL POSNET exposes (registered via
``php artisan pos:register-webhook``). Each request carries::

    X-Paylo-Event:      admin_reverse | bucket_expire
    X-Paylo-Event-Id:   <ulid>           # idempotency key for the receiver
    X-Paylo-Timestamp:  <unix>
    X-Paylo-Signature:  sha256=<hex>

POSNET MUST verify the HMAC signature in constant-time, enforce the ±5 min
timestamp window, and de-duplicate on ``X-Paylo-Event-Id``. This module owns
the verification half; deduplication is the receiver's problem (it depends on
the receiver's storage backend).

Design notes
------------
- Pure stdlib + Pydantic v2. No FastAPI / Starlette / framework coupling.
- Caller passes the raw body BYTES (whatever their HTTP server hands them) plus
  the header values. We do NOT re-decode JSON before verifying — the bytes that
  Paylo signed and the bytes on the wire must agree.
- Typed events: :class:`AdminReverseEvent` and :class:`BucketExpireEvent`. New
  event types are added here so consumers fail loudly on unknown shapes
  (e.g. a schema rollout you missed) rather than silently dropping data.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: Replay-window tolerance — matches Paylo's middleware (±300 s).
TIMESTAMP_SKEW_SECONDS = 300

#: HMAC signature header prefix. Distinguishes algorithm — if Paylo ever adds
#: BLAKE2 etc., callers can dispatch on this.
_SIG_PREFIX = "sha256="


class WebhookVerificationError(Exception):
    """Raised when the signature, timestamp, or headers fail validation. The
    receiver MUST respond ``401 Unauthorized`` and MUST NOT process the body."""


class WebhookEventError(Exception):
    """Raised when the body cannot be parsed into a known event shape. The
    receiver SHOULD respond ``400 Bad Request`` (so Paylo logs it as failed
    instead of retrying forever) but MUST NOT process the body."""


#
# Typed event models (one per event_type)
#


class AdminReverseEvent(BaseModel):
    """Fired when Paylo reverses a transaction outside POSNET's request flow
    (admin UI, manual web POS reverse). POSNET should update its local view to
    ``reversed`` so the next sale reflects the customer's actual balance."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: Literal["admin_reverse"]
    occurred_at: datetime
    transaction_id: int
    receipt_no: str
    merchant_id: int
    customer_id: int
    return_receipt_no: str
    reason: str | None = None
    reversed_at: datetime
    actor_id: int
    source: str


class BucketExpireEvent(BaseModel):
    """Fired when the nightly ``loyalty:expire-buckets`` cron expires a
    customer's per-merchant bonus balance. POSNET should update its local
    bucket cache so the kassir doesn't show stale 'redeem available' UI."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: Literal["bucket_expire"]
    occurred_at: datetime
    bucket_id: int
    merchant_id: int
    customer_id: int
    amount_expired_cents: int
    new_balance: int
    threshold: datetime
    expired_at: datetime


WebhookEvent = AdminReverseEvent | BucketExpireEvent


class WebhookVerifier:
    """Stateless verifier for inbound Paylo webhooks.

    Construct one per endpoint (each has its own ``hmac_secret``). The verifier
    holds no mutable state — safe to share across requests.
    """

    def __init__(self, secret: str, *, skew_seconds: int = TIMESTAMP_SKEW_SECONDS) -> None:
        if not secret:
            raise ValueError("webhook secret must not be empty")
        self._secret = secret.encode("utf-8")
        self._skew = skew_seconds

    def verify(
        self,
        *,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> None:
        """Raise :class:`WebhookVerificationError` on any failure; return on success.

        Splits into three checks so the caller's error message (and metrics)
        can attribute exactly which gate failed.
        """
        # Timestamp window — block replays.
        try:
            ts_int = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise WebhookVerificationError(f"malformed timestamp: {timestamp!r}") from exc
        if abs(int(time.time()) - ts_int) > self._skew:
            raise WebhookVerificationError("timestamp outside replay window")

        # Signature format.
        if not signature or not signature.startswith(_SIG_PREFIX):
            raise WebhookVerificationError("signature missing sha256= prefix")
        provided_hex = signature[len(_SIG_PREFIX) :]

        # HMAC match — constant time.
        payload = timestamp.encode("utf-8") + b"." + body
        expected_hex = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hex, provided_hex):
            raise WebhookVerificationError("signature mismatch")

    def verify_and_parse(
        self,
        *,
        body: bytes,
        timestamp: str,
        signature: str,
        event_type: str,
    ) -> WebhookEvent:
        """Verify then decode the body into the appropriate typed event.

        ``event_type`` is taken from the ``X-Paylo-Event`` header — we cross-
        validate it against the body's ``event_type`` field (a mismatch
        suggests tampering or a Paylo bug)."""
        self.verify(body=body, timestamp=timestamp, signature=signature)

        try:
            import json as _json

            raw = _json.loads(body)
        except ValueError as exc:
            raise WebhookEventError(f"body is not valid JSON: {exc}") from exc

        if not isinstance(raw, dict):
            raise WebhookEventError(f"body must be a JSON object, got {type(raw).__name__}")

        body_event_type = raw.get("event_type")
        if body_event_type != event_type:
            raise WebhookEventError(
                f"event_type header={event_type!r} does not match body={body_event_type!r}"
            )

        # Paylo wraps the domain payload under "data". Flatten for the event
        # model: top-level fields + spread of `data` -> event constructor.
        payload: dict[str, Any] = {
            "event_id": raw.get("event_id"),
            "event_type": event_type,
            "occurred_at": raw.get("occurred_at"),
            **(raw.get("data") or {}),
        }

        if event_type == "admin_reverse":
            return AdminReverseEvent.model_validate(payload)
        if event_type == "bucket_expire":
            return BucketExpireEvent.model_validate(payload)

        raise WebhookEventError(f"unknown event_type: {event_type!r}")
