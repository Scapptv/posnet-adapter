"""catalog: products + variants + product_images (AI-2.1)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_TABLES = ("products", "variants", "product_images")


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("store_id", _UUID, nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(length=200), nullable=True),
        sa.Column(
            "category_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'AZN'"), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False
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
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_tenant_id"), "products", ["tenant_id"], unique=False)
    # Full-text search on name (POS catalog lookup); 'simple' = no stemming, so it
    # works regardless of product-name language.
    op.execute(
        "CREATE INDEX ix_products_name_fts ON products USING gin (to_tsvector('simple', name))"
    )

    op.create_table(
        "variants",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("base_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("cost_price_minor", sa.BigInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "sku", name="uq_variants_product_sku"),
    )
    op.create_index(op.f("ix_variants_tenant_id"), "variants", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_variants_product_id"), "variants", ["product_id"], unique=False)
    op.create_index(op.f("ix_variants_sku"), "variants", ["sku"], unique=False)
    op.create_index(op.f("ix_variants_barcode"), "variants", ["barcode"], unique=False)

    op.create_table(
        "product_images",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("product_id", _UUID, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", _UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_images_tenant_id"), "product_images", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False
    )

    # New tables created after the 0002 blanket grant must be granted + RLS-enabled
    # individually (same pattern as 0004).
    for table in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO posnet_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    # Drop in FK order (child tables first); each DROP TABLE removes its indexes,
    # RLS policy and grants.
    op.drop_table("product_images")
    op.drop_table("variants")
    op.drop_table("products")
