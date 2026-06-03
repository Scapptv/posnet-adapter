"""Auth wiring (AI-1.9.3) — map core ``Settings`` into ``libs.auth`` primitives.

``libs.auth`` stays infrastructure-free (a plain ``AuthConfig`` dataclass); the
app is where env/Keycloak settings become a live :class:`TokenVerifier` (built
once in the lifespan, against the shared Redis client used for JWKS caching).
"""

from __future__ import annotations

from redis.asyncio import Redis

from libs.auth import AuthConfig, JwksClient, TokenVerifier

from .config import Settings

# Audience verification is optional only in these (non-deployed) environments;
# anywhere else a token's ``aud`` MUST be checked against a configured value
# (audit A7, ADR-0016) — empty audiences there is a misconfiguration.
_AUDIENCE_OPTIONAL_ENVS = frozenset({"local", "test"})


def build_auth_config(settings: Settings) -> AuthConfig:
    issuer = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
    audiences = tuple(a.strip() for a in settings.keycloak_audiences.split(",") if a.strip())
    if not audiences and settings.environment not in _AUDIENCE_OPTIONAL_ENVS:
        raise ValueError(
            "KEYCLOAK_AUDIENCES must be set outside local/test "
            f"(environment={settings.environment!r}); JWT audience is enforced (A7)"
        )
    return AuthConfig(
        issuer=issuer,
        jwks_url=f"{issuer}/protocol/openid-connect/certs",
        audiences=audiences,
        jwks_cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
    )


def build_token_verifier(settings: Settings, redis: Redis) -> TokenVerifier:
    config = build_auth_config(settings)
    return TokenVerifier(config, JwksClient(config, redis))
