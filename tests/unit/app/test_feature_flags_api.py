"""AI-1.17 — feature flag request schema + core registry (unit, no IO)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.core.app.api.v1.feature_flags import FlagUpdateRequest
from services.core.app.feature_flags import REGISTRY


@pytest.mark.unit
def test_update_request_requires_bool_enabled() -> None:
    assert FlagUpdateRequest(enabled=True).enabled is True


@pytest.mark.unit
@pytest.mark.parametrize("payload", [{}, {"enabled": True, "extra": 1}])
def test_update_request_rejects_invalid(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FlagUpdateRequest(**payload)


@pytest.mark.unit
def test_registry_declares_expected_flags() -> None:
    defaults = REGISTRY.defaults()
    assert defaults["marketplace_sync"] is False
    assert defaults["multi_store"] is True
