"""AI-1.9.1 — core Settings defaults + cached factory."""

from __future__ import annotations

import pytest

from services.core.app.config import Settings, get_settings


@pytest.mark.unit
def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "posnet-core"
    assert settings.redis_url.startswith("redis://")


@pytest.mark.unit
def test_get_settings_returns_settings() -> None:
    assert isinstance(get_settings(), Settings)
