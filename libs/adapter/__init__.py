"""Posnet channel-adapter contract (AI-2.5.1).

Every channel (Trendyol, Birmarket, Wolt, Bolt) implements one
:class:`ChannelAdapter` Protocol. The sync engine talks only to this surface —
adapters never reach into POS internals, the engine never knows a channel's
wire format. The Protocol is what makes "yeni kanal = 1 adapter + contract
test" the project's working contract (ADR-0012 §17.2).

Surface:

* :class:`ChannelAdapter` — the Protocol every adapter implements.
* :class:`AdapterCapabilities` — what the channel can do (push/pull, auth, rate
  limit). The sync engine reads it to decide which flows to schedule.
* :data:`registry` helpers — ``register_adapter`` / ``get_adapter`` /
  ``list_adapters`` so an adapter package can self-register on import and the
  sync engine can look it up by ``code`` (matches ``channels.code`` in the DB,
  ADR-0018 §3).
* :mod:`errors` — ``AdapterError`` hierarchy the sync engine classifies for
  retry / backoff / DLQ routing.
"""

from __future__ import annotations

from .capabilities import AdapterCapabilities, AuthKind
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .errors import (
    AdapterAuthError,
    AdapterError,
    AdapterPermanentError,
    AdapterRateLimitError,
    AdapterRetryableError,
)
from .hmac_verify import verify_signature
from .protocol import ChannelAdapter, ChannelListingResult
from .rate_limit import RateLimitTimeoutError, TokenBucket
from .registry import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
    clear_registry,
    get_adapter,
    list_adapters,
    register_adapter,
)

__all__ = [
    "AdapterAlreadyRegisteredError",
    "AdapterAuthError",
    "AdapterCapabilities",
    "AdapterError",
    "AdapterNotFoundError",
    "AdapterPermanentError",
    "AdapterRateLimitError",
    "AdapterRetryableError",
    "AuthKind",
    "ChannelAdapter",
    "ChannelListingResult",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "RateLimitTimeoutError",
    "TokenBucket",
    "clear_registry",
    "get_adapter",
    "list_adapters",
    "register_adapter",
    "verify_signature",
]
