"""AI-1.11 — per-request tenant resolution + RLS-scoped session (integration).

Full path: Bearer token -> real JWT verify (synthetic RSA + respx-mocked JWKS,
real Redis cache) -> subject resolved to tenant via ``users.external_subject``
-> session switched into ``posnet_app`` with ``app.current_tenant`` set -> RLS
isolates the query. A distinct issuer/kid keeps the shared-Redis JWKS cache from
colliding with ``test_auth``.
"""

from __future__ import annotations

import time

import httpx
import psycopg
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.app.api.deps import get_tenant_session
from services.core.app.config import Settings
from services.core.app.main import create_app

_KID = "it-key-1"
_KC_URL = "https://kc.it.test"
_ISSUER = f"{_KC_URL}/realms/posnet"
_JWKS_URL = f"{_ISSUER}/protocol/openid-connect/certs"


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


def _token(private_pem: str, *, subject: str, roles: list[str]) -> str:
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "sub": subject,
        "preferred_username": subject,
        "email": f"{subject}@posnet.test",
        "iat": now,
        "exp": now + 3600,
        "realm_access": {"roles": roles},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


def _seed_user(dsn: str, *, subject: str, email: str, status: str = "active") -> str:
    """Create a fresh tenant + one user (as owner -> RLS-exempt); return tenant id."""
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, country_code, plan) VALUES ('T','AZ','free') RETURNING id"
        )
        row = cur.fetchone()
        assert row is not None
        tenant_id = str(row[0])
        cur.execute(
            "INSERT INTO users (tenant_id, email, external_subject, status) "
            "VALUES (%s, %s, %s, %s)",
            (tenant_id, email, subject, status),
        )
    return tenant_id


def _build_app(pg_url: str, redis_url: str) -> FastAPI:
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_url,
            redis_url=redis_url,
            keycloak_url=_KC_URL,
            keycloak_realm="posnet",
        )
    )

    @app.get("/test/visible-users")
    async def _visible(
        request: Request, session: AsyncSession = Depends(get_tenant_session)
    ) -> dict[str, object]:
        result = await session.execute(text("SELECT email FROM users"))
        tenant_id = request.state.tenant_id
        return {
            "tenant_id": str(tenant_id) if tenant_id is not None else None,
            "emails": sorted(r[0] for r in result),
        }

    return app


def _call(app: FastAPI, jwks: dict[str, object], token: str) -> httpx.Response:
    with respx.mock:
        respx.get(_JWKS_URL).mock(return_value=httpx.Response(200, json=jwks))
        with TestClient(app) as client:
            return client.get("/test/visible-users", headers={"Authorization": f"Bearer {token}"})


@pytest.mark.integration
def test_tenant_user_sees_only_own_tenant(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    pg_dsn: str,
    redis_url: str,
    signing_key: tuple[str, str],
    jwks: dict[str, object],
) -> None:
    private_pem, _ = signing_key
    t1 = _seed_user(pg_dsn, subject="kc-iso-1", email="iso-u1@posnet.test")
    _seed_user(pg_dsn, subject="kc-iso-2", email="iso-u2@posnet.test")

    app = _build_app(pg_sqlalchemy_url, redis_url)
    response = _call(app, jwks, _token(private_pem, subject="kc-iso-1", roles=["tenant_admin"]))

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == t1
    assert "iso-u1@posnet.test" in body["emails"]
    assert "iso-u2@posnet.test" not in body["emails"]  # other tenant hidden by RLS


@pytest.mark.integration
def test_super_admin_sees_across_tenants(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    pg_dsn: str,
    redis_url: str,
    signing_key: tuple[str, str],
    jwks: dict[str, object],
) -> None:
    private_pem, _ = signing_key
    _seed_user(pg_dsn, subject="kc-sup-a", email="sup-a@posnet.test")
    _seed_user(pg_dsn, subject="kc-sup-b", email="sup-b@posnet.test")

    app = _build_app(pg_sqlalchemy_url, redis_url)
    # super_admin has no users row; resolution is skipped (cross-tenant, RLS-exempt).
    response = _call(app, jwks, _token(private_pem, subject="kc-super", roles=["super_admin"]))

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] is None
    assert {"sup-a@posnet.test", "sup-b@posnet.test"} <= set(body["emails"])


@pytest.mark.integration
def test_unknown_subject_is_forbidden(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    redis_url: str,
    signing_key: tuple[str, str],
    jwks: dict[str, object],
) -> None:
    private_pem, _ = signing_key
    app = _build_app(pg_sqlalchemy_url, redis_url)
    response = _call(app, jwks, _token(private_pem, subject="kc-ghost", roles=["tenant_admin"]))

    assert response.status_code == 403
    assert response.json()["status"] == 403


@pytest.mark.integration
def test_disabled_user_is_forbidden(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    pg_dsn: str,
    redis_url: str,
    signing_key: tuple[str, str],
    jwks: dict[str, object],
) -> None:
    private_pem, _ = signing_key
    _seed_user(pg_dsn, subject="kc-disabled", email="dis@posnet.test", status="disabled")

    app = _build_app(pg_sqlalchemy_url, redis_url)
    response = _call(app, jwks, _token(private_pem, subject="kc-disabled", roles=["cashier"]))

    assert response.status_code == 403  # status != active -> no tenant context
