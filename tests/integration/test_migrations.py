"""AI-1.5 — migration 0001 builds the identity schema; up/down/up cycle (G1)."""

from __future__ import annotations

import psycopg
import pytest
from alembic import command
from alembic.config import Config

_IDENTITY_TABLES = {
    "tenants",
    "stores",
    "users",
    "roles",
    "permissions",
    "user_roles",
    "audit_logs",
    "idempotency_keys",
    "outbox_events",
}


def _alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "services/core/alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _public_tables(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        return {row[0] for row in cur.fetchall()}


@pytest.mark.integration
def test_migration_up_down_up(pg_sqlalchemy_url: str, pg_dsn: str) -> None:
    cfg = _alembic_config(pg_sqlalchemy_url)

    command.upgrade(cfg, "head")
    assert _public_tables(pg_dsn) >= _IDENTITY_TABLES

    command.downgrade(cfg, "base")
    assert not (_IDENTITY_TABLES & _public_tables(pg_dsn))

    command.upgrade(cfg, "head")
    assert _public_tables(pg_dsn) >= _IDENTITY_TABLES
