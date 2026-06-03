"""AI-2.H1 — JWT audience enforcement outside local/test (A7, ADR-0017).

``build_auth_config`` refuses to build a verifier that skips audience checks in a
deployed environment: an empty ``KEYCLOAK_AUDIENCES`` there is a misconfiguration.
"""

from __future__ import annotations

import pytest

from services.core.app.config import Settings
from services.core.app.security import build_auth_config


@pytest.mark.unit
def test_audience_required_outside_local() -> None:
    with pytest.raises(ValueError, match="KEYCLOAK_AUDIENCES"):
        build_auth_config(Settings(environment="production", keycloak_audiences=""))


@pytest.mark.unit
def test_audience_optional_in_local() -> None:
    cfg = build_auth_config(Settings(environment="local", keycloak_audiences=""))
    assert cfg.audiences == ()


@pytest.mark.unit
def test_audience_used_when_configured_outside_local() -> None:
    cfg = build_auth_config(
        Settings(environment="production", keycloak_audiences="api-gateway,account")
    )
    assert cfg.audiences == ("api-gateway", "account")
