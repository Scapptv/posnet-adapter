"""inventory: warehouses + inventory + stock_movements (AI-2.2)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_TABLES = ("warehouses", "inventory", "stock_movements")


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=20), server_default=sa.text("'store'"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_warehouses_tenant_id"), "warehouses", ["tenant_id"], unique=False)

    op.create_table(
        "inventory",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("variant_id", _UUID, nullable=False),
        sa.Column("warehouse_id", _UUID, nullable=False),
        sa.Column("qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("min_qty", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant_id", "warehouse_id", name="uq_inventory_variant_warehouse"),
    )
    op.create_index(op.f("ix_inventory_tenant_id"), "inventory", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_inventory_variant_id"), "inventory", ["variant_id"], unique=False)

    op.create_table(
        "stock_movements",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("variant_id", _UUID, nullable=False),
        sa.Column("warehouse_id", _UUID, nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("qty", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column(
            "moved_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_movements_tenant_id"), "stock_movements", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_stock_movements_variant_id"), "stock_movements", ["variant_id"], unique=False
    )
    op.create_index(
        op.f("ix_stock_movements_moved_at"), "stock_movements", ["moved_at"], unique=False
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
    op.drop_table("stock_movements")
    op.drop_table("inventory")
    op.drop_table("warehouses")
