"""Unit tests for the adapter error hierarchy (AI-2.5.1).

The sync engine relies on isinstance checks against these types to pick the
right retry/DLQ branch, so the hierarchy is part of the contract.
"""

from __future__ import annotations

import pytest

from libs.adapter import (
    AdapterAuthError,
    AdapterError,
    AdapterPermanentError,
    AdapterRateLimitError,
    AdapterRetryableError,
)


@pytest.mark.unit
def test_rate_limit_is_retryable() -> None:
    """``AdapterRateLimitError`` is a retryable subtype — a sync engine
    branching on ``isinstance(exc, AdapterRetryableError)`` catches both."""
    exc = AdapterRateLimitError("slow down", retry_after_seconds=30)
    assert isinstance(exc, AdapterRetryableError)
    assert isinstance(exc, AdapterError)
    assert exc.retry_after_seconds == 30


@pytest.mark.unit
def test_auth_and_permanent_are_not_retryable() -> None:
    """Auth and permanent errors must NOT inherit from ``AdapterRetryableError``
    — otherwise the engine would retry them forever."""
    assert not issubclass(AdapterAuthError, AdapterRetryableError)
    assert not issubclass(AdapterPermanentError, AdapterRetryableError)
    assert issubclass(AdapterAuthError, AdapterError)
    assert issubclass(AdapterPermanentError, AdapterError)


@pytest.mark.unit
@pytest.mark.parametrize(
    "cls",
    [
        AdapterError,
        AdapterRetryableError,
        AdapterRateLimitError,
        AdapterAuthError,
        AdapterPermanentError,
    ],
)
def test_error_carries_message_and_default_retry_after(cls: type[AdapterError]) -> None:
    exc = cls("boom")
    assert exc.message == "boom"
    assert exc.retry_after_seconds is None
    assert str(exc) == "boom"
