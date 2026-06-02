"""Auth configuration (AI-1.8).

A plain dataclass — libs stay infrastructure-free; the app maps env/Keycloak
settings into it (AI-1.9). ``issuer`` must equal the ``iss`` claim the token
carries (mind Keycloak's internal-vs-external hostname: the configured issuer
has to match what clients actually receive).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    jwks_url: str
    # Empty -> audience is not verified (foundation default; enable with an
    # audience mapper on the realm for production, ADR-0014).
    audiences: tuple[str, ...] = ()
    algorithms: tuple[str, ...] = ("RS256",)
    jwks_cache_ttl_seconds: int = 3600
    # Clock-skew tolerance for exp/nbf/iat.
    leeway_seconds: int = 30

    @classmethod
    def from_env(cls) -> AuthConfig:
        base = os.environ.get("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
        realm = os.environ.get("KEYCLOAK_REALM", "posnet")
        issuer = f"{base}/realms/{realm}"
        audiences = tuple(a for a in os.environ.get("KEYCLOAK_AUDIENCES", "").split(",") if a)
        return cls(
            issuer=issuer,
            jwks_url=f"{issuer}/protocol/openid-connect/certs",
            audiences=audiences,
            jwks_cache_ttl_seconds=int(os.environ.get("JWKS_CACHE_TTL_SECONDS", "3600")),
        )
