"""rls policies

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, tenant-scoping column). The app connects as the non-owner role
# ``posnet_app`` so RLS applies; each request does
# ``SELECT set_config('app.current_tenant', <uuid>, false)`` (AI-1.11).
_RLS_TABLES: list[tuple[str, str]] = [
    ("tenants", "id"),
    ("stores", "tenant_id"),
    ("users", "tenant_id"),
    ("roles", "tenant_id"),
    ("permissions", "tenant_id"),
    ("user_roles", "tenant_id"),
    ("audit_logs", "tenant_id"),
    ("idempotency_keys", "tenant_id"),
    ("outbox_events", "tenant_id"),
]


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'posnet_app') THEN "
        "CREATE ROLE posnet_app NOLOGIN; END IF; END $$;"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO posnet_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO posnet_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO posnet_app")
    for table, col in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({col} = current_setting('app.current_tenant', true)::uuid) "
            f"WITH CHECK ({col} = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    for table, _col in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM posnet_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM posnet_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM posnet_app")
    op.execute("DROP ROLE IF EXISTS posnet_app")
