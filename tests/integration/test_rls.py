"""AI-1.6 — RLS tenant isolation: cross-tenant rows are invisible / rejected."""

from __future__ import annotations

import psycopg
import pytest
from alembic import command
from alembic.config import Config


def _migrate(url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "services/core/alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _seed_two_tenants(dsn: str) -> tuple[str, str]:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, country_code, plan) VALUES ('T1','AZ','free') RETURNING id"
        )
        row1 = cur.fetchone()
        cur.execute(
            "INSERT INTO tenants (name, country_code, plan) VALUES ('T2','AZ','free') RETURNING id"
        )
        row2 = cur.fetchone()
        assert row1 is not None
        assert row2 is not None
        t1, t2 = str(row1[0]), str(row2[0])
        cur.execute("INSERT INTO users (tenant_id, email) VALUES (%s, 'u1@example.com')", (t1,))
        cur.execute("INSERT INTO users (tenant_id, email) VALUES (%s, 'u2@example.com')", (t2,))
    return t1, t2


@pytest.mark.integration
def test_rls_select_isolation(pg_sqlalchemy_url: str, pg_dsn: str) -> None:
    _migrate(pg_sqlalchemy_url)
    t1, t2 = _seed_two_tenants(pg_dsn)

    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET ROLE posnet_app")
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (t1,))
        cur.execute("SELECT tenant_id FROM users")
        seen_t1 = {str(r[0]) for r in cur.fetchall()}
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (t2,))
        cur.execute("SELECT tenant_id FROM users")
        seen_t2 = {str(r[0]) for r in cur.fetchall()}

    assert seen_t1 == {t1}
    assert seen_t2 == {t2}


@pytest.mark.integration
def test_rls_insert_with_check_rejects_cross_tenant(pg_sqlalchemy_url: str, pg_dsn: str) -> None:
    _migrate(pg_sqlalchemy_url)
    t1, t2 = _seed_two_tenants(pg_dsn)

    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SET ROLE posnet_app")
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (t1,))
        with pytest.raises(psycopg.Error):
            cur.execute(
                "INSERT INTO users (tenant_id, email) VALUES (%s, 'evil@example.com')", (t2,)
            )
