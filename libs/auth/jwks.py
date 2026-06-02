"""JWKS fetching with a Redis cache (AI-1.8).

Keycloak signs with rotating keys; we cache the realm's JWKS in Redis (TTL from
config) and look the signing key up by ``kid``. A ``kid`` miss triggers exactly
one refetch (key rotation) before giving up — so rotation heals without a
restart, but an unknown key still fails fast.

A JWKS fetch failure (Keycloak down) propagates as an httpx error, not an
``AuthError`` — it is an availability problem, not a bad token.
"""

from __future__ import annotations

from typing import Any

import httpx
import orjson
from redis.asyncio import Redis

from libs.common import AuthError

from .config import AuthConfig


class JwksClient:
    def __init__(self, config: AuthConfig, redis: Redis) -> None:
        self._config = config
        self._redis = redis
        self._cache_key = f"auth:jwks:{config.issuer}"

    async def get_key(self, kid: str) -> dict[str, Any]:
        keys = await self._load(refresh=False)
        if kid not in keys:
            keys = await self._load(refresh=True)  # likely rotation -> refetch once
        if kid not in keys:
            raise AuthError(f"unknown signing key: {kid}")
        return keys[kid]

    async def _load(self, *, refresh: bool) -> dict[str, dict[str, Any]]:
        if not refresh:
            cached = await self._redis.get(self._cache_key)
            if cached is not None:
                return self._index(orjson.loads(cached))
        jwks = await self._fetch()
        await self._redis.set(
            self._cache_key, orjson.dumps(jwks), ex=self._config.jwks_cache_ttl_seconds
        )
        return self._index(jwks)

    async def _fetch(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._config.jwks_url)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload

    @staticmethod
    def _index(jwks: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {key["kid"]: key for key in jwks.get("keys", []) if "kid" in key}
