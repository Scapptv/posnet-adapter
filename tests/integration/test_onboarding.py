"""AI-1.15 — tenant onboarding domain + API (integration, real DB + RLS).

Domain/seed run on the owner session factory (RLS-exempt cross-tenant write); the
endpoint goes through the full app with a real super_admin token (synthetic RSA +
respx-mocked JWKS, distinct issuer so the shared Redis JWKS cache stays isolated).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import psycopg
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.core.app.config import Settings
from services.core.app.domain.onboarding import (
    TENANT_ONBOARDED,
    onboard_tenant,
    seed_first_tenant,
)
from services.core.app.main import create_app

_KID = "onb-key-1"
_KC_URL = "https://kc.onb.test"
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


def _token(private_pem: str, *, roles: list[str], subject: str = "kc-caller") -> str:
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


def _build_app(pg_url: str, redis_url: str) -> FastAPI:
    return create_app(
        Settings(
            environment="local",
            database_url=pg_url,
            redis_url=redis_url,
            keycloak_url=_KC_URL,
            keycloak_realm="posnet",
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        )
    )


@pytest.fixture
def mocked_jwks(jwks: dict[str, object]) -> Iterator[None]:
    with respx.mock:
        respx.get(_JWKS_URL).mock(return_value=httpx.Response(200, json=jwks))
        yield


# ---- domain ----


@pytest.mark.integration
async def test_onboard_tenant_creates_records_and_event(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with async_session_factory() as session, session.begin():
        result = await onboard_tenant(
            session,
            name="Acme",
            country_code="AZ",
            plan="pro",
            admin_email="admin@acme.az",
            admin_subject="kc-acme-admin",
        )

    assert result.name == "Acme"
    assert result.status == "active"

    async with async_session_factory() as session:
        tenant = (
            await session.execute(
                text("SELECT name, plan, status FROM tenants WHERE id = :id"),
                {"id": str(result.tenant_id)},
            )
        ).first()
        user = (
            await session.execute(
                text("SELECT email, external_subject, tenant_id FROM users WHERE id = :id"),
                {"id": str(result.admin_user_id)},
            )
        ).first()
        event = (
            await session.execute(
                text(
                    "SELECT count(*) FROM outbox_events WHERE event_type = :t AND tenant_id = :tid"
                ),
                {"t": TENANT_ONBOARDED, "tid": str(result.tenant_id)},
            )
        ).scalar_one()

    assert tenant is not None and tenant.plan == "pro" and tenant.status == "active"
    assert user is not None and user.email == "admin@acme.az"
    assert user.external_subject == "kc-acme-admin"
    assert str(user.tenant_id) == str(result.tenant_id)
    assert event == 1  # onboarded event enqueued atomically


@pytest.mark.integration
async def test_seed_first_tenant_is_idempotent(
    migrated_db: None, async_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subject = "kc-seed-idem"
    fields = {
        "name": "Seed Co",
        "country_code": "AZ",
        "plan": "pro",
        "admin_email": "seed@x.az",
        "admin_subject": subject,
    }
    async with async_session_factory() as session, session.begin():
        first = await seed_first_tenant(session, **fields)
    async with async_session_factory() as session, session.begin():
        again = await seed_first_tenant(session, **fields)

    assert first is not None
    assert again is None  # already seeded -> skipped

    async with async_session_factory() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM users WHERE external_subject = :s"), {"s": subject}
            )
        ).scalar_one()
    assert count == 1


# ---- endpoint ----


@pytest.mark.integration
def test_onboard_endpoint_super_admin_creates_tenant(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    pg_dsn: str,
    redis_url: str,
    signing_key: tuple[str, str],
    mocked_jwks: None,
) -> None:
    private_pem, _ = signing_key
    app = _build_app(pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:
        response = client.post(
            "/v1/tenants",
            json={
                "name": "Endpoint Co",
                "country_code": "az",  # normalised to AZ
                "admin_email": "EP@Co.AZ",  # normalised to lower
                "admin_subject": "kc-ep-admin",
            },
            headers={"Authorization": f"Bearer {_token(private_pem, roles=['super_admin'])}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Endpoint Co"
    assert body["status"] == "active"

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT email, external_subject, country_code FROM users "
            "JOIN tenants ON tenants.id = users.tenant_id WHERE users.id = %s",
            (body["admin_user_id"],),
        )
        row = cur.fetchone()
    assert row == ("ep@co.az", "kc-ep-admin", "AZ")


@pytest.mark.integration
def test_onboard_endpoint_forbidden_for_cashier(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    redis_url: str,
    signing_key: tuple[str, str],
    mocked_jwks: None,
) -> None:
    private_pem, _ = signing_key
    app = _build_app(pg_sqlalchemy_url, redis_url)
    with TestClient(app) as client:
        response = client.post(
            "/v1/tenants",
            json={
                "name": "X",
                "country_code": "AZ",
                "admin_email": "x@x.az",
                "admin_subject": "kc-cashier-attempt",
            },
            headers={"Authorization": f"Bearer {_token(private_pem, roles=['cashier'])}"},
        )
    assert response.status_code == 403


@pytest.mark.integration
def test_onboard_endpoint_duplicate_subject_conflicts(
    migrated_db: None,
    pg_sqlalchemy_url: str,
    redis_url: str,
    signing_key: tuple[str, str],
    mocked_jwks: None,
) -> None:
    private_pem, _ = signing_key
    app = _build_app(pg_sqlalchemy_url, redis_url)
    token = _token(private_pem, roles=["super_admin"])
    body = {
        "name": "Dup Co",
        "country_code": "AZ",
        "admin_email": "dup@co.az",
        "admin_subject": "kc-dup-admin",
    }
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        first = client.post("/v1/tenants", json=body, headers=headers)
        second = client.post(
            "/v1/tenants", json={**body, "admin_email": "dup2@co.az"}, headers=headers
        )

    assert first.status_code == 201
    assert second.status_code == 409  # duplicate external_subject
