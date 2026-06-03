"""AI-1.7 — posnet realm config: RBAC roles, client topology, seed user, no secrets.

Structural guard for ``infra/keycloak/realm-posnet.json``. The live OIDC
round-trip (token issuance + verification) lands with the verifier in AI-1.8.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_REALM: dict[str, Any] = json.loads(
    (Path(__file__).parents[3] / "infra" / "keycloak" / "realm-posnet.json").read_text(
        encoding="utf-8"
    )
)


def _client(client_id: str) -> dict[str, Any]:
    return next(c for c in _REALM["clients"] if c["clientId"] == client_id)


@pytest.mark.unit
def test_realm_identity() -> None:
    assert _REALM["realm"] == "posnet"
    assert _REALM["enabled"] is True


@pytest.mark.unit
def test_rbac_roles_match_section_15() -> None:
    names = {r["name"] for r in _REALM["roles"]["realm"]}
    assert names == {"super_admin", "tenant_admin", "store_manager", "cashier", "clerk"}


@pytest.mark.unit
def test_three_clients() -> None:
    assert {c["clientId"] for c in _REALM["clients"]} == {
        "posnet-web",
        "posnet-pos",
        "api-gateway",
    }


@pytest.mark.unit
def test_frontend_clients_are_public_with_pkce() -> None:
    for client_id in ("posnet-web", "posnet-pos"):
        client = _client(client_id)
        assert client["publicClient"] is True
        assert client["attributes"]["pkce.code.challenge.method"] == "S256"


@pytest.mark.unit
def test_pos_client_allows_direct_access_for_dev() -> None:
    assert _client("posnet-pos")["directAccessGrantsEnabled"] is True


@pytest.mark.unit
def test_api_client_is_bearer_only() -> None:
    assert _client("api-gateway")["bearerOnly"] is True


@pytest.mark.unit
def test_no_client_holds_a_secret() -> None:
    # Foundation is secret-free (ADR-0014): every client is public or bearer-only.
    for client in _REALM["clients"]:
        assert "secret" not in client
        assert client.get("publicClient") or client.get("bearerOnly")


@pytest.mark.unit
def test_seed_user_has_tenant_admin_role() -> None:
    owner = next(u for u in _REALM["users"] if u["username"] == "owner")
    assert "tenant_admin" in owner["realmRoles"]


@pytest.mark.unit
def test_seed_user_password_is_env_placeholder_not_literal() -> None:
    # A6 (ADR-0016): no hardcoded credential in this public file. The dev owner
    # password is substituted from the environment at realm-import time.
    owner = next(u for u in _REALM["users"] if u["username"] == "owner")
    cred = next(c for c in owner["credentials"] if c["type"] == "password")
    assert cred["value"].startswith("${env."), cred["value"]
