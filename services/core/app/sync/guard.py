"""Per-channel rate-limit + circuit-breaker guard (AI-2.5.6.2).

Two callers make throttled, breaker-protected calls to a channel adapter:

* the sync **dispatcher** (AI-2.5.2) — outbound push from the change feed, and
* the **reconciliation** job (AI-2.5.6.2) — drift detect + repair.

The *throttling + breaker* are identical for both; the *error policy* differs.
The consumer-driven dispatcher re-raises retryable errors so the consumer's
backoff fires; the batch reconcile skips the offending listing and moves on.
So ``ChannelGuard`` owns only the shared part — per-channel
:class:`~libs.adapter.TokenBucket` + :class:`~libs.adapter.CircuitBreaker`
keyed by channel id — and :meth:`call` *raises* the underlying exception, letting
each caller layer its own policy on top.

State (the buckets + breakers) lives on the guard instance, so it persists
across calls for a guard's lifetime (one per dispatcher / one per reconcile run).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from libs.adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    CircuitBreaker,
    TokenBucket,
)


@dataclass(frozen=True, slots=True)
class GuardConfig:
    """Per-channel rate-limit / circuit-breaker tunables.

    Defaults are conservative — a real channel that needs faster rates passes
    its own config (e.g. derived from ``AdapterCapabilities.rate_limit_rps``).
    """

    rate_per_second: float = 1.0
    rate_burst: int = 1
    rate_acquire_timeout_seconds: float = 30.0
    breaker_fail_max: int = 5
    breaker_reset_seconds: float = 60.0


class ChannelGuard:
    """Owns per-channel token buckets + circuit breakers, keyed by channel id."""

    def __init__(self, config: GuardConfig | None = None) -> None:
        self._config = config or GuardConfig()
        self._limiters: dict[UUID, TokenBucket] = {}
        self._breakers: dict[UUID, CircuitBreaker] = {}

    def _limiter_for(self, channel_id: UUID) -> TokenBucket:
        limiter = self._limiters.get(channel_id)
        if limiter is None:
            limiter = TokenBucket(
                rate_per_second=self._config.rate_per_second,
                capacity=self._config.rate_burst,
            )
            self._limiters[channel_id] = limiter
        return limiter

    def _breaker_for(self, channel_id: UUID) -> CircuitBreaker:
        breaker = self._breakers.get(channel_id)
        if breaker is None:
            breaker = CircuitBreaker(
                fail_max=self._config.breaker_fail_max,
                reset_timeout=self._config.breaker_reset_seconds,
                # Don't trip the breaker on non-retryable errors — they're caused
                # by bad payloads or stale credentials, not a sick upstream.
                excluded_exceptions=(AdapterAuthError, AdapterPermanentError),
            )
            self._breakers[channel_id] = breaker
        return breaker

    async def call(
        self, channel_id: UUID, op: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        """Run ``op`` under ``channel_id``'s rate limit + circuit breaker.

        Raises the adapter's exception (an ``AdapterError`` subclass) or
        :class:`~libs.adapter.CircuitBreakerOpenError` — the caller decides
        whether to retry, skip, or swallow.
        """
        await self._limiter_for(channel_id).acquire(
            timeout=self._config.rate_acquire_timeout_seconds
        )
        return await self._breaker_for(channel_id).call(op, *args, **kwargs)
