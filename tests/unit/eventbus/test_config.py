"""AI-1.14 — EventBusConfig defaults and exponential backoff math."""

from __future__ import annotations

import pytest

from libs.eventbus import EventBusConfig, backoff_seconds


@pytest.mark.unit
def test_config_defaults() -> None:
    cfg = EventBusConfig()
    assert cfg.queue == "posnet_events"
    assert cfg.dlq == "posnet_events_dlq"
    assert cfg.max_retries == 5
    assert cfg.set_tenant_context is True


@pytest.mark.unit
def test_backoff_grows_exponentially() -> None:
    delays = [backoff_seconds(ct, base=2, cap=300) for ct in (1, 2, 3, 4, 5)]
    assert delays == [2, 4, 8, 16, 32]


@pytest.mark.unit
def test_backoff_is_capped() -> None:
    assert backoff_seconds(20, base=2, cap=300) == 300


@pytest.mark.unit
def test_backoff_floors_read_ct_at_one() -> None:
    # A zero/negative read_ct must not collapse the delay to base**0 == 1's edge.
    assert backoff_seconds(0, base=2, cap=300) == 2
