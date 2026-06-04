"""Unit tests for the Vault token loader.

We don't spin up a real Vault here (that's an integration test); we stub
``libs.vault.get_secret`` so we can assert exactly which reference would have
been requested and how errors propagate.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from libs.loyalty_client import (
    LoyaltyClient,
    client_from_vault,
    load_token,
    rotate_client,
    token_ref_for,
)
from libs.vault.client import SecretError


@pytest.mark.unit
def test_token_ref_for_builds_canonical_path() -> None:
    assert token_ref_for("m_412") == "vault://secret/posnet/loyalty/m_412/token"
    assert token_ref_for("m_209") == "vault://secret/posnet/loyalty/m_209/token"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "with space", "has/slash"])
def test_token_ref_for_rejects_invalid_merchant_code(bad: str) -> None:
    with pytest.raises(ValueError):
        token_ref_for(bad)


@pytest.mark.unit
def test_load_token_resolves_canonical_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        captured["ref"] = ref
        return "tok_from_vault_aaaabbbb"

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)
    assert load_token("m_412") == "tok_from_vault_aaaabbbb"
    assert captured["ref"] == "vault://secret/posnet/loyalty/m_412/token"


@pytest.mark.unit
def test_load_token_propagates_secret_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_secret(ref: str, *, config: object = None) -> str:
        raise SecretError("secret not found")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)
    with pytest.raises(SecretError):
        load_token("m_404")


@pytest.mark.unit
async def test_client_from_vault_carries_loaded_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return "vault_tok_xxxxx"
        # HMAC secret path raises "not present" — represents legacy token
        # issued without --require-hmac (no paired secret in Vault).
        raise SecretError("key 'hmac_secret' not present in secret")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    async with client_from_vault("m_412", base_url="https://paylo.test") as client:
        assert client._token == "vault_tok_xxxxx"
        assert client._hmac_secret is None
        assert isinstance(client, LoyaltyClient)


@pytest.mark.unit
@respx.mock
async def test_client_from_vault_sends_loaded_token_on_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end check: the token loaded from Vault MUST appear in the
    Authorization header on every outbound request. No silent fallback."""

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return "vault_tok_yyyy"
        raise SecretError("key 'hmac_secret' not present in secret")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    route = respx.post("https://paylo.test/api/v1/pos/customer/lookup").mock(
        return_value=httpx.Response(
            200, json={"status": "not_found", "customer": None, "bucket": None}
        )
    )

    async with client_from_vault("m_412", base_url="https://paylo.test") as client:
        await client.lookup_customer(qr="qr_xxx")

    assert route.calls.last.request.headers["authorization"] == "Bearer vault_tok_yyyy"


@pytest.mark.unit
async def test_rotate_client_replaces_token_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hot-rotation path — long-running services pick up new Vault values
    without dropping their httpx connection pool."""

    token_secrets = iter(["old_token", "new_token"])

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return next(token_secrets)
        raise SecretError("key 'hmac_secret' not present in secret")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    async with client_from_vault("m_412", base_url="https://paylo.test") as client:
        assert client._token == "old_token"
        rotate_client(client, "m_412")
        assert client._token == "new_token"


@pytest.mark.unit
async def test_client_from_vault_loads_hmac_secret_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vault has both a token and a paired hmac_secret — the client picks up
    both and signs subsequent requests."""

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return "tok-with-hmac"
        if ref.endswith("/hmac_secret"):
            return "0123456789abcdef" * 4  # 64 hex chars
        raise SecretError("unknown ref")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    async with client_from_vault("m_412", base_url="https://paylo.test") as client:
        assert client._token == "tok-with-hmac"
        assert client._hmac_secret == "0123456789abcdef" * 4
