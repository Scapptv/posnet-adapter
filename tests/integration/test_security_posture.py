"""AI-2.H1 — DB security posture (audit A1 fix, ADR-0017).

The app's per-request pool connects as the non-owner, NOBYPASSRLS role
``posnet_app``; a forgotten tenant scope then returns *zero* rows (RLS), never
another tenant's data. RLS is FORCE'd on every tenant table. The one inherently
cross-tenant lookup (subject -> tenant) goes through a SECURITY DEFINER function.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit, urlunsplit

import httpx
import psycopg
import pytest
import respx
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.app.api.deps import get_tenant_session
from services.core.app.config import Settings
from services.core.app.main import create_app

from .test_tenant_context import _generate_pem  # reuse the synthetic-RSA helper

_POOL_KID = "pool-kid"

APP_ROLE = "posnet_app"
APP_PASSWORD = "posnet_app_dev_pw"  # pragma: allowlist secret  (migration 0009 dev default)


def _migrate(url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "services/core/alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _app_role_dsn(superuser_dsn: str) -> str:
    """Swap the superuser credentials for the ``posnet_app`` login (same host/db)."""
    parts = urlsplit(superuser_dsn)
    netloc = f"{APP_ROLE}:{APP_PASSWORD}@{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _seed_tenant_user(dsn: str, *, subject: str, email: str) -> str:
    """Create a fresh tenant + active user (as owner -> RLS-exempt); return tenant id."""
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, country_code, plan) VALUES ('T','AZ','free') RETURNING id"
        )
        row = cur.fetchone()
        assert row is not None
        tenant_id = str(row[0])
        cur.execute(
            "INSERT INTO users (tenant_id, email, external_subject, status) "
            "VALUES (%s, %s, %s, 'active')",
            (tenant_id, email, subject),
        )
    return tenant_id


@pytest.mark.integration
def test_app_role_is_login_nonowner_nobypassrls(migrated_db: None, pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            (APP_ROLE,),
        )
        row = cur.fetchone()
    assert row is not None
    can_login, is_super, bypass_rls = row
    assert can_login is True  # the app connects as this role
    assert is_super is False  # not a superuser
    assert bypass_rls is False  # cannot bypass RLS -> the second layer holds


@pytest.mark.integration
def test_rls_forced_on_every_policy_table(migrated_db: None, pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND c.relrowsecurity AND NOT c.relforcerowsecurity"
        )
        not_forced = sorted(r[0] for r in cur.fetchall())
    assert not_forced == []  # every RLS-enabled table is also FORCE'd


@pytest.mark.integration
def test_app_role_without_tenant_sees_zero_rows(migrated_db: None, pg_dsn: str) -> None:
    """The regression: connecting as the locked-down role with no tenant scope
    returns nothing (RLS), rather than leaking every tenant's rows."""
    _seed_tenant_user(pg_dsn, subject="sec-zero", email="sec-zero@x.az")
    with psycopg.connect(_app_role_dsn(pg_dsn), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM users")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 0


@pytest.mark.integration
def test_app_role_scoped_sees_only_its_tenant(migrated_db: None, pg_dsn: str) -> None:
    t1 = _seed_tenant_user(pg_dsn, subject="sec-scope-1", email="sec-s1@x.az")
    _seed_tenant_user(pg_dsn, subject="sec-scope-2", email="sec-s2@x.az")
    with psycopg.connect(_app_role_dsn(pg_dsn), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (t1,))
        cur.execute("SELECT tenant_id FROM users")
        seen = {str(r[0]) for r in cur.fetchall()}
    assert seen == {t1}


@pytest.mark.integration
def test_resolver_bypasses_rls_for_subject_lookup(migrated_db: None, pg_dsn: str) -> None:
    """The locked-down role cannot read ``users`` cross-tenant, but may call the
    SECURITY DEFINER resolver — the one allowed cross-tenant lookup."""
    t1 = _seed_tenant_user(pg_dsn, subject="sec-resolve", email="sec-r@x.az")
    with psycopg.connect(_app_role_dsn(pg_dsn), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM users")  # no tenant set -> empty
        row = cur.fetchone()
        assert row is not None and row[0] == 0
        cur.execute("SELECT posnet_resolve_tenant('sec-resolve')")
        resolved = cur.fetchone()
        assert resolved is not None and str(resolved[0]) == t1
        cur.execute("SELECT posnet_resolve_tenant('ghost-subject')")
        missing = cur.fetchone()
        assert missing is not None and missing[0] is None


_KC_URL = "https://kc.pool.test"
_ISSUER = f"{_KC_URL}/realms/posnet"
_JWKS_URL = f"{_ISSUER}/protocol/openid-connect/certs"


def _jwks(public_pem: str) -> dict[str, object]:
    entry = {
        k: (v.decode() if isinstance(v, bytes) else v)
        for k, v in jwk.construct(public_pem, "RS256").to_dict().items()
    }
    entry.update({"kid": _POOL_KID, "use": "sig", "alg": "RS256"})
    return {"keys": [entry]}


def _token(private_pem: str, *, subject: str) -> str:
    now = int(time.time())
    claims = {
        "iss": _ISSUER,
        "sub": subject,
        "preferred_username": subject,
        "email": f"{subject}@posnet.test",
        "iat": now,
        "exp": now + 3600,
        "realm_access": {"roles": ["tenant_admin"]},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _POOL_KID})


def _build_pool_app(pg_url: str, app_pool_url: str, redis_url: str) -> FastAPI:
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_url,
            database_app_url=app_pool_url,  # real non-owner pool
            redis_url=redis_url,
            keycloak_url=_KC_URL,
            keycloak_realm="posnet",
            rate_limit_storage_uri="memory://",
            eventbus_enabled=False,
        )
    )

    @app.get("/test/pool-users")
    async def _users(
        request: Request, session: AsyncSession = Depends(get_tenant_session)
    ) -> dict[str, object]:
        result = await session.execute(text("SELECT email FROM users"))
        return {"emails": sorted(r[0] for r in result)}

    return app


@pytest.mark.integration
def test_app_pool_request_isolates_by_tenant(
    migrated_db: None, pg_sqlalchemy_url: str, pg_dsn: str, redis_url: str
) -> None:
    """End-to-end: an app built with the non-owner app pool still isolates a
    regular tenant request (the SECURITY DEFINER resolution works on it)."""
    private_pem, public_pem = _generate_pem()
    _seed_tenant_user(pg_dsn, subject="kc-pool-1", email="pool-1@x.az")
    _seed_tenant_user(pg_dsn, subject="kc-pool-2", email="pool-2@x.az")

    app = _build_pool_app(pg_sqlalchemy_url, _app_role_dsn(pg_sqlalchemy_url), redis_url)
    with respx.mock:
        respx.get(_JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(public_pem)))
        with TestClient(app) as client:
            resp = client.get(
                "/test/pool-users",
                headers={"Authorization": f"Bearer {_token(private_pem, subject='kc-pool-1')}"},
            )

    assert resp.status_code == 200, resp.text
    emails = resp.json()["emails"]
    assert "pool-1@x.az" in emails
    assert "pool-2@x.az" not in emails  # other tenant hidden by RLS on the app pool
