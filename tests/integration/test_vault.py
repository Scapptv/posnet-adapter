"""AI-1.3 — get_secret against a real Vault (KV-v2, dev mode via testcontainers)."""

from __future__ import annotations

import hvac
import pytest

from libs.vault import SecretError, VaultClient, VaultConfig, resolve_ref


def _seed(config: VaultConfig, path: str, secret: dict[str, str]) -> None:
    client = hvac.Client(url=config.addr, token=config.token)
    client.secrets.kv.v2.create_or_update_secret(path=path, secret=secret, mount_point="secret")


@pytest.mark.integration
def test_get_secret_reads_kv_v2_value(vault_config: VaultConfig) -> None:
    _seed(vault_config, "posnet/db", {"password": "db-pass-123"})  # pragma: allowlist secret
    value = VaultClient(vault_config).get_secret("vault://secret/posnet/db/password")
    assert value == "db-pass-123"  # pragma: allowlist secret


@pytest.mark.integration
def test_get_secret_resolves_deep_path(vault_config: VaultConfig) -> None:
    secret = {"api_key": "bm-key"}  # pragma: allowlist secret
    _seed(vault_config, "posnet/channels/birmarket", secret)
    value = VaultClient(vault_config).get_secret("vault://secret/posnet/channels/birmarket/api_key")
    assert value == "bm-key"


@pytest.mark.integration
def test_missing_secret_raises(vault_config: VaultConfig) -> None:
    with pytest.raises(SecretError, match="not found"):
        VaultClient(vault_config).get_secret("vault://secret/posnet/does-not-exist/x")


@pytest.mark.integration
def test_missing_key_raises(vault_config: VaultConfig) -> None:
    _seed(vault_config, "posnet/db", {"password": "p"})  # pragma: allowlist secret
    with pytest.raises(SecretError, match="not present"):
        VaultClient(vault_config).get_secret("vault://secret/posnet/db/username")


@pytest.mark.integration
def test_forbidden_token_raises(vault_config: VaultConfig) -> None:
    _seed(vault_config, "posnet/db", {"password": "p"})  # pragma: allowlist secret
    bad = VaultConfig(addr=vault_config.addr, token="wrong-token")  # pragma: allowlist secret
    with pytest.raises(SecretError, match="cannot read"):
        VaultClient(bad).get_secret("vault://secret/posnet/db/password")


@pytest.mark.integration
def test_resolve_ref_resolves_reference(vault_config: VaultConfig) -> None:
    _seed(vault_config, "posnet/db", {"password": "via-resolve"})  # pragma: allowlist secret
    assert resolve_ref("vault://secret/posnet/db/password", config=vault_config) == "via-resolve"
