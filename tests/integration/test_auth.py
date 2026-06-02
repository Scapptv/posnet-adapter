"""AI-1.8 — JWKS cache + JWT verification.

Synthetic RSA keys + respx-mocked JWKS + real Redis (testcontainers). This
exercises the full verifier without booting Keycloak; the live Keycloak round
trip is a separate concern. Keys are generated, the public half is published as
a JWKS, tokens are signed with the private half.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from redis.asyncio import Redis

from libs.auth import AuthConfig, JwksClient, TokenVerifier
from libs.common import AuthError

_KID = "test-key-1"
_ISSUER = "https://kc.test/realms/posnet"
_JWKS_URL = "https://kc.test/realms/posnet/protocol/openid-connect/certs"


def _generate_pem() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(scope="module")
def signing_key() -> tuple[str, str]:
    return _generate_pem()


@pytest.fixture(scope="module")
def jwks(signing_key: tuple[str, str]) -> dict[str, object]:
    _, public_pem = signing_key
    entry = {
        k: (v.decode() if isinstance(v, bytes) else v)
        for k, v in jwk.construct(public_pem, "RS256").to_dict().items()
    }
    entry.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"keys": [entry]}


def _token(
    private_pem: str,
    *,
    roles: list[str],
    iss: str = _ISSUER,
    exp_delta: int = 3600,
    kid: str = _KID,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "sub": "user-123",
        "preferred_username": "owner",
        "email": "owner@posnet.test",
        "iat": now,
        "exp": now + exp_delta,
        "realm_access": {"roles": roles},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


def _config() -> AuthConfig:
    return AuthConfig(issuer=_ISSUER, jwks_url=_JWKS_URL)


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def mocked_jwks(jwks: dict[str, object]) -> Iterator[respx.Route]:
    with respx.mock:
        route = respx.get(_JWKS_URL).mock(return_value=httpx.Response(200, json=jwks))
        yield route


@pytest.mark.integration
async def test_jwks_fetched_once_then_cached(redis_client: Redis, mocked_jwks: respx.Route) -> None:
    client = JwksClient(_config(), redis_client)
    first = await client.get_key(_KID)
    second = await client.get_key(_KID)
    assert first["kid"] == _KID
    assert second["kid"] == _KID
    assert mocked_jwks.call_count == 1  # second lookup served from Redis


@pytest.mark.integration
async def test_verify_valid_token(
    signing_key: tuple[str, str], redis_client: Redis, mocked_jwks: respx.Route
) -> None:
    private_pem, _ = signing_key
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    principal = await verifier.verify(_token(private_pem, roles=["tenant_admin", "clerk"]))
    assert principal.subject == "user-123"
    assert principal.username == "owner"
    assert principal.email == "owner@posnet.test"
    assert principal.has_role("tenant_admin")


@pytest.mark.integration
async def test_expired_token_rejected(
    signing_key: tuple[str, str], redis_client: Redis, mocked_jwks: respx.Route
) -> None:
    private_pem, _ = signing_key
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(_token(private_pem, roles=["cashier"], exp_delta=-120))


@pytest.mark.integration
async def test_wrong_issuer_rejected(
    signing_key: tuple[str, str], redis_client: Redis, mocked_jwks: respx.Route
) -> None:
    private_pem, _ = signing_key
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(_token(private_pem, roles=["cashier"], iss="https://evil/realms/x"))


@pytest.mark.integration
async def test_bad_signature_rejected(redis_client: Redis, mocked_jwks: respx.Route) -> None:
    # Sign with a different key but claim the published kid -> signature mismatch.
    other_private, _ = _generate_pem()
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(_token(other_private, roles=["cashier"]))


@pytest.mark.integration
async def test_unknown_kid_refetches_then_rejects(
    signing_key: tuple[str, str], redis_client: Redis, mocked_jwks: respx.Route
) -> None:
    private_pem, _ = signing_key
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(_token(private_pem, roles=["cashier"], kid="rotated-kid"))
    assert mocked_jwks.call_count == 2  # initial fetch + one refresh on kid miss


@pytest.mark.integration
async def test_malformed_token_rejected(redis_client: Redis) -> None:
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify("not-a-valid-jwt")


@pytest.mark.integration
async def test_token_without_kid_rejected(
    signing_key: tuple[str, str], redis_client: Redis
) -> None:
    private_pem, _ = signing_key
    now = int(time.time())
    no_kid = jwt.encode(
        {"iss": _ISSUER, "sub": "x", "exp": now + 60}, private_pem, algorithm="RS256"
    )
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(no_kid)


@pytest.mark.integration
async def test_unsupported_alg_rejected(redis_client: Redis) -> None:
    now = int(time.time())
    hs256 = jwt.encode(
        {"iss": _ISSUER, "sub": "x", "exp": now + 60},
        "unused-hmac-key",
        algorithm="HS256",
        headers={"kid": _KID},
    )
    verifier = TokenVerifier(_config(), JwksClient(_config(), redis_client))
    with pytest.raises(AuthError):
        await verifier.verify(hs256)
