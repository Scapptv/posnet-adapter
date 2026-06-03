"""pricing: price_overrides (AI-2.3)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "price_overrides",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("variant_id", _UUID, nullable=False),
        sa.Column("store_id", _UUID, nullable=True),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
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
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_price_overrides_tenant_id"), "price_overrides", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_price_overrides_variant_id"), "price_overrides", ["variant_id"], unique=False
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON price_overrides TO posnet_app")
    op.execute("ALTER TABLE price_overrides ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON price_overrides "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.drop_table("price_overrides")
