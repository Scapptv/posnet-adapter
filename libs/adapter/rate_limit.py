"""Per-channel token-bucket rate limiter (AI-2.5.2).

The sync dispatcher acquires a token from a per-channel bucket before each
adapter call. Token capacity = ``rate_limit_burst``; refill rate =
``rate_limit_rps`` tokens per second — matches ``AdapterCapabilities`` so a
channel that says "5 rps with burst of 10" is honoured literally.

Bucket math runs under an ``asyncio.Lock`` so concurrent dispatcher tasks see
a consistent token count. ``acquire`` either takes a token immediately or
sleeps until one is available; callers that cannot tolerate the wait pass
``timeout=`` and handle :class:`RateLimitTimeoutError`.
"""

from __future__ import annotations

import asyncio
from time import monotonic


class RateLimitTimeoutError(TimeoutError):
    """The bucket did not refill within ``timeout`` seconds — caller decides
    whether to retry, requeue, or surface to the channel."""


class TokenBucket:
    """Async, fair, monotonic-clock token bucket.

    *Fair* — ``asyncio.Lock`` queues callers FIFO; no caller starves under
    sustained pressure.

    *Monotonic* — uses ``time.monotonic()``, so a wall-clock skew (NTP
    adjustment, leap second) never makes the bucket think it has refilled
    when it hasn't.
    """

    __slots__ = ("_capacity", "_last_refill", "_lock", "_rps", "_tokens")

    def __init__(self, *, rate_per_second: float, capacity: int) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be > 0")
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = capacity
        self._rps = rate_per_second
        self._tokens = float(capacity)  # full at start — first burst is free
        self._last_refill = monotonic()
        self._lock = asyncio.Lock()

    @property
    def available_tokens(self) -> float:
        """Last-observed token count (may be stale until ``_refill`` runs)."""
        return self._tokens

    async def acquire(self, *, timeout: float | None = None) -> None:
        """Block until a token is available, then take it.

        ``timeout`` (seconds) caps the wait. If the bucket can't refill in that
        time, raises :class:`RateLimitTimeoutError` without consuming a token.

        (ASYNC109: ``timeout`` is part of this rate-limiter's API — callers
        configure a per-call budget rather than wrapping each acquire in
        ``asyncio.timeout``. The internal implementation does use
        ``asyncio.timeout``.)
        """
        try:
            async with asyncio.timeout(timeout):
                await self._acquire_one()
        except TimeoutError as exc:
            raise RateLimitTimeoutError("token bucket exhausted") from exc

    async def _acquire_one(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Time until next token becomes available
                wait = (1.0 - self._tokens) / self._rps
                await asyncio.sleep(wait)

    def _refill(self) -> None:
        now = monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rps)
        self._last_refill = now
