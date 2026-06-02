"""Posnet auth (AI-1.8) — verify Keycloak JWTs, expose roles, gate access.

``TokenVerifier.verify`` turns a Bearer token into a :class:`Principal` (RS256
checked against the JWKS, cached in Redis); ``require_role`` / ``require_permission``
gate on the principal. FastAPI dependency wiring lands with the app (AI-1.9).
"""

from __future__ import annotations

from .config import AuthConfig
from .jwks import JwksClient
from .principal import SUPER_ADMIN, Principal
from .rbac import ROLE_PERMISSIONS, has_permission, require_permission, require_role
from .verifier import TokenVerifier

__all__ = [
    "ROLE_PERMISSIONS",
    "SUPER_ADMIN",
    "AuthConfig",
    "JwksClient",
    "Principal",
    "TokenVerifier",
    "has_permission",
    "require_permission",
    "require_role",
]
