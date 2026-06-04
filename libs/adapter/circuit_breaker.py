"""Async circuit breaker (AI-2.5.2).

Classic three-state breaker — CLOSED → OPEN → HALF_OPEN — sized for one channel.
The sync dispatcher wraps every adapter call in ``call`` so a sustained outage
trips the breaker and skips dispatches instead of piling up retries.

We hand-roll this (~40 lines of state machine) because the upstream
``pybreaker.CircuitBreaker.call_async`` carries a Tornado dependency it never
imports — calling it under asyncio raises ``NameError: gen``. The behaviour we
need is small and well-defined; the library cost is not worth the workaround.

States:

* **CLOSED** — calls pass through, failures are counted. After
  ``fail_max`` consecutive failures the breaker trips to OPEN.
* **OPEN** — calls raise :class:`CircuitBreakerOpenError` immediately.
  After ``reset_timeout`` seconds the breaker transitions to HALF_OPEN.
* **HALF_OPEN** — exactly one trial call is allowed through. Success closes
  the breaker; failure re-opens it for another ``reset_timeout``.

Exception classification is the caller's job: pass ``excluded_exceptions=`` so
expected-control-flow errors (e.g. auth / permanent) don't trip the breaker.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from time import monotonic
from typing import Any


class CircuitBreakerOpenError(Exception):
    """Raised by :meth:`CircuitBreaker.call` when the breaker is OPEN."""


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    __slots__ = (
        "_excluded",
        "_fail_count",
        "_fail_max",
        "_opened_at",
        "_reset_timeout",
        "_state",
    )

    def __init__(
        self,
        *,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        excluded_exceptions: tuple[type[BaseException], ...] = (),
    ) -> None:
        if fail_max <= 0:
            raise ValueError("fail_max must be > 0")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be > 0")
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._excluded = excluded_exceptions
        self._state = _State.CLOSED
        self._fail_count = 0
        self._opened_at = 0.0

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def fail_count(self) -> int:
        return self._fail_count

    async def call(
        self,
        func: Callable[..., Awaitable[Any]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``func`` under breaker rules. Raises
        :class:`CircuitBreakerOpenError` when the breaker is OPEN; re-raises
        whatever ``func`` raised otherwise (and updates state accordingly)."""
        self._maybe_recover()
        if self._state is _State.OPEN:
            raise CircuitBreakerOpenError("circuit breaker is open")
        try:
            result = await func(*args, **kwargs)
        except BaseException as exc:
            if not isinstance(exc, self._excluded):
                self._record_failure()
            raise
        self._record_success()
        return result

    def _maybe_recover(self) -> None:
        if self._state is _State.OPEN and monotonic() - self._opened_at >= self._reset_timeout:
            self._state = _State.HALF_OPEN

    def _record_failure(self) -> None:
        if self._state is _State.HALF_OPEN:
            # Trial call failed — back to OPEN, restart the cooldown.
            self._open()
            return
        self._fail_count += 1
        if self._fail_count >= self._fail_max:
            self._open()

    def _record_success(self) -> None:
        # Any success — half-open trial or steady-state — resets the counter
        # and closes the breaker. Half a heartbeat-success in HALF_OPEN
        # promotes to CLOSED.
        self._state = _State.CLOSED
        self._fail_count = 0

    def _open(self) -> None:
        self._state = _State.OPEN
        self._opened_at = monotonic()
