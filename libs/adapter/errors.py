"""Adapter error hierarchy (AI-2.5.1).

The sync engine catches every adapter exception and classifies it by *kind*
to decide what to do:

* :class:`AdapterRetryableError` — transient (5xx, network hiccup) → exponential
  backoff, requeue.
* :class:`AdapterRateLimitError` — channel said 429 → use ``retry_after`` (if
  provided) for the backoff floor.
* :class:`AdapterAuthError` — channel said 401/403 → DLQ + alert; nothing
  retries until the operator rotates the credential.
* :class:`AdapterPermanentError` — channel said 400/404 / payload nonsense →
  DLQ; future deliveries with the same payload will hit the same wall.

Adapter implementations raise the right subclass; the engine never looks at
HTTP status codes.
"""

from __future__ import annotations


class AdapterError(Exception):
    """Base for everything an adapter may raise.

    The sync engine catches ``AdapterError`` (and nothing else) to apply
    retry/DLQ policy. Bare ``Exception``s bubble up as a "framework bug" and
    crash the worker — exactly what we want, since it isn't an expected
    channel-side condition.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds


class AdapterRetryableError(AdapterError):
    """Transient failure — the engine should retry with backoff."""


class AdapterRateLimitError(AdapterRetryableError):
    """Channel rate-limited the call (HTTP 429 or equivalent).

    A retryable error with a hint: ``retry_after_seconds`` (from the channel's
    ``Retry-After`` header) is the floor for the next attempt's delay.
    """


class AdapterAuthError(AdapterError):
    """Channel rejected our credentials (HTTP 401 / 403).

    Not retryable: re-trying the same auth header will get the same answer.
    The engine routes to DLQ and surfaces an operator alert; nothing recovers
    until the credential is rotated.
    """


class AdapterPermanentError(AdapterError):
    """Channel rejected the request as malformed or unknown (HTTP 400 / 404 /
    422-style).

    Not retryable: the payload itself is the problem. The engine routes to
    DLQ so an operator can inspect the offending message.
    """
