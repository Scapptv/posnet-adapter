"""JWT verification against Keycloak's JWKS (AI-1.8).

Verifies signature (RS256 via the JWKS key matching the token ``kid``), issuer
and expiry, then projects the claims into a :class:`Principal`. Any failure
raises :class:`~libs.common.AuthError` (401) — never leaks the jose error type.
"""

from __future__ import annotations

from typing import Any

from jose import jwt
from jose.exceptions import JWTError

from libs.common import AuthError

from .config import AuthConfig
from .jwks import JwksClient
from .principal import Principal


class TokenVerifier:
    def __init__(self, config: AuthConfig, jwks_client: JwksClient) -> None:
        self._config = config
        self._jwks = jwks_client

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise AuthError("malformed token") from exc

        kid = header.get("kid")
        if not kid:
            raise AuthError("token header missing kid")
        if header.get("alg") not in self._config.algorithms:
            raise AuthError(f"unsupported token alg: {header.get('alg')}")

        key = await self._jwks.get_key(kid)
        audiences = self._config.audiences
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._config.algorithms),
                issuer=self._config.issuer,
                audience=audiences[0] if audiences else None,
                options={
                    "leeway": self._config.leeway_seconds,
                    "verify_aud": bool(audiences),
                    # Reject tokens missing the temporal/identity claims outright
                    # (a token without exp/iat/sub must not be treated as valid).
                    "require_exp": True,
                    "require_iat": True,
                    "require_sub": True,
                },
            )
        except JWTError as exc:
            raise AuthError(f"token rejected: {exc}") from exc

        return self._to_principal(claims)

    @staticmethod
    def _to_principal(claims: dict[str, Any]) -> Principal:
        # ``require_sub`` guarantees the claim is present; reject an empty one too
        # (an empty subject cannot identify a principal -> no tenant resolution).
        subject = str(claims.get("sub", "")).strip()
        if not subject:
            raise AuthError("token has empty subject")
        realm_access = claims.get("realm_access") or {}
        return Principal(
            subject=subject,
            username=claims.get("preferred_username"),
            email=claims.get("email"),
            roles=frozenset(realm_access.get("roles", [])),
        )
