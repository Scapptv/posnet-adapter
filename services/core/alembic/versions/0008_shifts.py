"""sales: shifts/vardiya + cash_movements (AI-2.4)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_TABLES = ("shifts", "cash_movements")


def upgrade() -> None:
    op.create_table(
        "shifts",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("store_id", _UUID, nullable=False),
        sa.Column("cashier_id", _UUID, nullable=False),
        sa.Column("status", sa.String(length=10), server_default=sa.text("'open'"), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'AZN'"), nullable=False),
        sa.Column("opening_cash_minor", sa.BigInteger(), nullable=False),
        sa.Column("closing_cash_minor", sa.BigInteger(), nullable=True),
        sa.Column(
            "opened_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cashier_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shifts_tenant_id"), "shifts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_shifts_store_id"), "shifts", ["store_id"], unique=False)
    # At most one open shift per (store, cashier).
    op.create_index(
        "uq_shifts_open",
        "shifts",
        ["store_id", "cashier_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "cash_movements",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("shift_id", _UUID, nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cash_movements_tenant_id"), "cash_movements", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_cash_movements_shift_id"), "cash_movements", ["shift_id"], unique=False
    )

    for table in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO posnet_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    op.drop_table("cash_movements")
    op.drop_table("shifts")
