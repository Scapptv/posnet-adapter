"""AI-1.1 — test harness sanity (unit, fast)."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_harness_runs() -> None:
    assert 1 + 1 == 2


@pytest.mark.unit
async def test_async_harness_runs() -> None:
    """asyncio_mode=auto -> async tests run automatically."""
    assert True
