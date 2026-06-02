"""Vault secret resolution (AI-1.3).

Code never embeds secrets — it carries a ``vault://`` reference and resolves it
at startup (ADR-0003, CLAUDE.md). Reference grammar::

    vault://<mount>/<path...>/<key>

The first segment is the KV mount, the last is the key inside the secret, and
everything between is the secret path. So ``vault://secret/posnet/db/password``
reads key ``password`` from KV-v2 secret ``posnet/db`` on mount ``secret``; and
``vault://secret/posnet/channels/birmarket/api_key`` reads ``api_key`` from
``posnet/channels/birmarket``.

Secret *values* are never cached (they rotate) and never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import hvac
from hvac.exceptions import InvalidPath, VaultError

_SCHEME = "vault://"


class SecretError(Exception):
    """A secret reference is malformed or cannot be resolved."""


@dataclass(frozen=True)
class VaultConfig:
    addr: str = "http://localhost:8200"
    token: str = ""
    namespace: str = ""

    @classmethod
    def from_env(cls) -> VaultConfig:
        return cls(
            addr=os.environ.get("VAULT_ADDR", "http://localhost:8200"),
            token=os.environ.get("VAULT_TOKEN", ""),
            namespace=os.environ.get("VAULT_NAMESPACE", ""),
        )


def parse_ref(ref: str) -> tuple[str, str, str]:
    """Split a ``vault://`` reference into ``(mount, path, key)``."""
    if not ref.startswith(_SCHEME):
        raise SecretError(f"not a vault reference (missing {_SCHEME!r} scheme): {ref!r}")
    segments = [s for s in ref[len(_SCHEME) :].split("/") if s]
    if len(segments) < 3:
        raise SecretError(f"vault reference needs mount/path/key: {ref!r}")
    mount, *path_parts, key = segments
    return mount, "/".join(path_parts), key


class VaultClient:
    """Thin hvac wrapper that resolves ``vault://`` references to KV-v2 values."""

    def __init__(self, config: VaultConfig | None = None) -> None:
        self._config = config or VaultConfig.from_env()
        self._client = hvac.Client(
            url=self._config.addr,
            token=self._config.token,
            namespace=self._config.namespace or None,
        )

    def get_secret(self, ref: str) -> str:
        mount, path, key = parse_ref(ref)
        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=mount, raise_on_deleted_version=True
            )
        except InvalidPath as exc:
            raise SecretError(f"secret not found: {_SCHEME}{mount}/{path}") from exc
        except VaultError as exc:
            raise SecretError(f"cannot read {_SCHEME}{mount}/{path}: {exc}") from exc

        data = response["data"]["data"]
        if key not in data:
            raise SecretError(f"key {key!r} not present in secret {_SCHEME}{mount}/{path}")
        return str(data[key])


def get_secret(ref: str, *, config: VaultConfig | None = None) -> str:
    """Resolve a single ``vault://`` reference (uses ``VAULT_*`` env by default)."""
    return VaultClient(config).get_secret(ref)


def resolve_ref(value: str, *, config: VaultConfig | None = None) -> str:
    """Resolve ``value`` if it is a ``vault://`` reference, else return it as-is.

    Lets config fields hold either a literal or a reference, so callers need not
    special-case the prefix.
    """
    if value.startswith(_SCHEME):
        return get_secret(value, config=config)
    return value
