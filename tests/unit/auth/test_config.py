"""AI-1.8 — AuthConfig.from_env (issuer/jwks construction, audience parsing)."""

from __future__ import annotations

import pytest

from libs.auth import AuthConfig


@pytest.mark.unit
def test_from_env_builds_issuer_and_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_URL", "http://kc:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "posnet")
    monkeypatch.delenv("KEYCLOAK_AUDIENCES", raising=False)
    cfg = AuthConfig.from_env()
    assert cfg.issuer == "http://kc:8080/realms/posnet"
    assert cfg.jwks_url == "http://kc:8080/realms/posnet/protocol/openid-connect/certs"
    assert cfg.audiences == ()


@pytest.mark.unit
def test_from_env_parses_audiences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_URL", "http://kc:8080/")  # trailing slash tolerated
    monkeypatch.setenv("KEYCLOAK_AUDIENCES", "api-gateway,account")
    cfg = AuthConfig.from_env()
    assert cfg.issuer == "http://kc:8080/realms/posnet"
    assert cfg.audiences == ("api-gateway", "account")
