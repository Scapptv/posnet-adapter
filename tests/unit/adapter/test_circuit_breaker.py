"""Unit tests for the hand-rolled async CircuitBreaker (AI-2.5.2)."""

from __future__ import annotations

import asyncio

import pytest

from libs.adapter import CircuitBreaker, CircuitBreakerOpenError


class _BoomError(Exception):
    pass


class _SkippedError(Exception):
    pass


@pytest.mark.unit
def test_rejects_bad_config() -> None:
    with pytest.raises(ValueError, match="fail_max"):
        CircuitBreaker(fail_max=0)
    with pytest.raises(ValueError, match="reset_timeout"):
        CircuitBreaker(fail_max=1, reset_timeout=0)


@pytest.mark.unit
async def test_closed_breaker_passes_calls_through() -> None:
    breaker = CircuitBreaker(fail_max=3)

    async def _ok() -> int:
        return 42

    assert await breaker.call(_ok) == 42
    assert breaker.state == "closed"


@pytest.mark.unit
async def test_breaker_opens_after_fail_max() -> None:
    breaker = CircuitBreaker(fail_max=2, reset_timeout=10.0)

    async def _boom() -> None:
        raise _BoomError("nope")

    for _ in range(2):
        with pytest.raises(_BoomError):
            await breaker.call(_boom)
    assert breaker.state == "open"

    # Now the breaker short-circuits without calling _boom at all.
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(_boom)


@pytest.mark.unit
async def test_breaker_recovers_to_half_open_after_reset() -> None:
    breaker = CircuitBreaker(fail_max=1, reset_timeout=0.05)

    async def _boom() -> None:
        raise _BoomError("first failure")

    with pytest.raises(_BoomError):
        await breaker.call(_boom)
    assert breaker.state == "open"

    await asyncio.sleep(0.06)  # past the reset cooldown

    async def _ok() -> str:
        return "recovered"

    # Successful trial in HALF_OPEN closes the breaker.
    assert await breaker.call(_ok) == "recovered"
    assert breaker.state == "closed"


@pytest.mark.unit
async def test_half_open_failure_re_opens() -> None:
    breaker = CircuitBreaker(fail_max=1, reset_timeout=0.05)

    async def _boom() -> None:
        raise _BoomError("die")

    with pytest.raises(_BoomError):
        await breaker.call(_boom)
    await asyncio.sleep(0.06)

    # Trial call fails — breaker goes back to OPEN.
    with pytest.raises(_BoomError):
        await breaker.call(_boom)
    assert breaker.state == "open"


@pytest.mark.unit
async def test_excluded_exceptions_do_not_trip_breaker() -> None:
    """Auth / permanent errors aren't channel sickness — they shouldn't
    contribute to the breaker's failure budget."""
    breaker = CircuitBreaker(fail_max=2, excluded_exceptions=(_SkippedError,))

    async def _excluded() -> None:
        raise _SkippedError("ignored")

    for _ in range(10):
        with pytest.raises(_SkippedError):
            await breaker.call(_excluded)
    assert breaker.state == "closed"
    assert breaker.fail_count == 0


@pytest.mark.unit
async def test_success_resets_failure_count() -> None:
    """One success after a streak of failures (still below fail_max) wipes the
    slate — flaky channels stay open."""
    breaker = CircuitBreaker(fail_max=5)

    async def _boom() -> None:
        raise _BoomError("flap")

    async def _ok() -> str:
        return "fine"

    for _ in range(3):
        with pytest.raises(_BoomError):
            await breaker.call(_boom)
    await breaker.call(_ok)
    assert breaker.fail_count == 0
    assert breaker.state == "closed"
