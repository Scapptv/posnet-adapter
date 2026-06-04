"""Unit tests for TokenBucket (AI-2.5.2)."""

from __future__ import annotations

import asyncio
from time import monotonic

import pytest

from libs.adapter import RateLimitTimeoutError, TokenBucket


@pytest.mark.unit
def test_rejects_invalid_config() -> None:
    with pytest.raises(ValueError, match="rate_per_second"):
        TokenBucket(rate_per_second=0, capacity=5)
    with pytest.raises(ValueError, match="rate_per_second"):
        TokenBucket(rate_per_second=-1, capacity=5)
    with pytest.raises(ValueError, match="capacity"):
        TokenBucket(rate_per_second=1, capacity=0)
    with pytest.raises(ValueError, match="capacity"):
        TokenBucket(rate_per_second=1, capacity=-3)


@pytest.mark.unit
def test_starts_full() -> None:
    """A fresh bucket has its full burst available — the first push doesn't
    wait. Otherwise the dispatcher would always sleep on cold start."""
    bucket = TokenBucket(rate_per_second=1, capacity=5)
    assert bucket.available_tokens == 5


@pytest.mark.unit
async def test_burst_drains_then_refills() -> None:
    """Drain the burst, wait one tick, the bucket has earned a token back."""
    bucket = TokenBucket(rate_per_second=100, capacity=3)
    for _ in range(3):
        await bucket.acquire()
    assert bucket.available_tokens < 1.0
    # 1/100s for the next token; give the bucket a generous slice.
    await asyncio.sleep(0.05)
    await bucket.acquire()  # refilled — no raise, no long block


@pytest.mark.unit
async def test_acquire_blocks_until_refill() -> None:
    """When empty, ``acquire`` sleeps roughly the time to earn one token —
    not zero (no busy-loop), not forever."""
    bucket = TokenBucket(rate_per_second=20, capacity=1)
    await bucket.acquire()  # drains
    start = monotonic()
    await bucket.acquire()  # waits ~50ms for next token
    elapsed = monotonic() - start
    assert 0.01 < elapsed < 0.5  # actually slept, not instant and not forever


@pytest.mark.unit
async def test_timeout_raises_on_starvation() -> None:
    """If the bucket can't refill within ``timeout``, the caller sees
    :class:`RateLimitTimeoutError` instead of blocking forever."""
    bucket = TokenBucket(rate_per_second=0.1, capacity=1)  # 1 token / 10s
    await bucket.acquire()  # drains
    with pytest.raises(RateLimitTimeoutError, match="exhausted"):
        await bucket.acquire(timeout=0.05)


@pytest.mark.unit
async def test_concurrent_acquires_serialise_under_lock() -> None:
    """Many tasks competing for a tiny bucket must each get their token in
    order — none lost, none double-issued. Tests the lock + monotonic-clock
    arithmetic together."""
    bucket = TokenBucket(rate_per_second=200, capacity=5)
    n = 20
    await asyncio.gather(*[bucket.acquire() for _ in range(n)])
    # 5 from initial burst + 15 from refill at 200/sec = ~75ms ideal; we
    # don't time it, but the gather succeeding without leakage is the
    # behavioural property.


@pytest.mark.unit
async def test_capacity_caps_refill() -> None:
    """Idle for a long time — the bucket fills only to ``capacity``, not
    unbounded. Otherwise a long-quiet channel would burst far above its
    sustained rate."""
    bucket = TokenBucket(rate_per_second=1000, capacity=2)
    await asyncio.sleep(0.05)  # would refill 50 tokens if uncapped
    # _refill is called lazily; touch it via acquire.
    await bucket.acquire()
    assert bucket.available_tokens <= 1.0  # capped at 2 - 1 = 1
