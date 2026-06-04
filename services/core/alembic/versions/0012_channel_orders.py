"""channel_orders — inbound webhook ingest (AI-2.5.4, roadmap §17.3 inbound)

Stores every channel order the hub has ever received. The channel's own
``channel_order_id`` is unique per channel — the second delivery of the same
webhook is dropped at the constraint, giving us at-least-once → exactly-once
without an application-side lookup-then-insert race.

Lifecycle (``status``):
- ``received`` — webhook landed, HMAC verified, canonical payload normalised
- ``reserved`` — inventory reservation applied (AI-2.5.5)
- ``fulfilled`` — POS shipped the line(s) (AI-2.5.5)
- ``rejected`` — payload accepted but cannot be honoured (e.g. unknown SKU,
  oversold) — kept for audit (AI-2.5.5)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "channel_orders",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("channel_id", _UUID, nullable=False),
        sa.Column("channel_order_id", sa.String(length=200), nullable=False),
        sa.Column(
            "canonical_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'received'"), nullable=False
        ),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # The exact-once guarantee: a redelivered webhook trips this constraint.
        sa.UniqueConstraint(
            "channel_id", "channel_order_id", name="uq_channel_orders_channel_order"
        ),
    )
    op.create_index(
        op.f("ix_channel_orders_tenant_id"), "channel_orders", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_channel_orders_channel_id"), "channel_orders", ["channel_id"], unique=False
    )
    op.create_index(
        op.f("ix_channel_orders_received_at"),
        "channel_orders",
        ["received_at"],
        unique=False,
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON channel_orders TO posnet_app")
    op.execute("ALTER TABLE channel_orders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE channel_orders FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON channel_orders "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.drop_table("channel_orders")
