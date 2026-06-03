"""feature flags (per-tenant overrides, AI-1.17)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_feature_flags_tenant_key"),
    )
    op.create_index(
        op.f("ix_feature_flags_tenant_id"), "feature_flags", ["tenant_id"], unique=False
    )

    # The 0002 blanket GRANT only covered tables existing then; a table created
    # later must be granted to the RLS role explicitly (no default privileges set).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flags TO posnet_app")
    op.execute("ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON feature_flags "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    # DROP TABLE also removes its index, RLS policy and grants.
    op.drop_index(op.f("ix_feature_flags_tenant_id"), table_name="feature_flags")
    op.drop_table("feature_flags")
