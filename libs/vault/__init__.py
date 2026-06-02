"""Posnet Vault helper (AI-1.3) — resolve ``vault://`` references to secrets."""

from __future__ import annotations

from .client import (
    SecretError,
    VaultClient,
    VaultConfig,
    get_secret,
    parse_ref,
    resolve_ref,
)

__all__ = [
    "SecretError",
    "VaultClient",
    "VaultConfig",
    "get_secret",
    "parse_ref",
    "resolve_ref",
]
