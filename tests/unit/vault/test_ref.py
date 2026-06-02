"""AI-1.3 — vault:// reference grammar + resolve_ref passthrough (no IO)."""

from __future__ import annotations

import pytest

from libs.vault import SecretError, VaultConfig, parse_ref, resolve_ref


@pytest.mark.unit
def test_parse_ref_splits_mount_path_key() -> None:
    assert parse_ref("vault://secret/posnet/db/password") == ("secret", "posnet/db", "password")


@pytest.mark.unit
def test_parse_ref_supports_deep_paths() -> None:
    assert parse_ref("vault://secret/posnet/channels/birmarket/api_key") == (
        "secret",
        "posnet/channels/birmarket",
        "api_key",
    )


@pytest.mark.unit
def test_parse_ref_rejects_missing_scheme() -> None:
    with pytest.raises(SecretError, match="scheme"):
        parse_ref("secret/posnet/db/password")


@pytest.mark.unit
def test_parse_ref_rejects_too_few_segments() -> None:
    with pytest.raises(SecretError, match="mount/path/key"):
        parse_ref("vault://secret/password")


@pytest.mark.unit
def test_resolve_ref_passes_through_literal() -> None:
    # No vault:// prefix -> returned untouched, no Vault call.
    assert resolve_ref("plain-literal-value") == "plain-literal-value"


@pytest.mark.unit
def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULT_ADDR", "http://vault.example:8200")
    monkeypatch.setenv("VAULT_TOKEN", "tok")  # pragma: allowlist secret
    monkeypatch.setenv("VAULT_NAMESPACE", "team-a")
    cfg = VaultConfig.from_env()
    assert cfg.addr == "http://vault.example:8200"
    assert cfg.token == "tok"  # pragma: allowlist secret
    assert cfg.namespace == "team-a"
