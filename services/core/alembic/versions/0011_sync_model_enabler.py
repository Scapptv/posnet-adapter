"""sync model enabler: online-sellable / online-published + channels + channel_listings (AI-2.H5)

ADR-0018 implementation (audit B2/B3/B4/B6):

- ``warehouses.is_online_sellable`` (default true) — anbar onlayn satışa
  açıqdırmı? Online aggregation yalnız ``is_online_sellable=true`` anbarlardan
  toplayır. Default ``true`` mövcud davranışı qoruyur.
- ``products.online_published`` (default false) — məhsul onlayn vitrində?
  Default ``false`` çünki inadvertent push qarşısını alır; ``build_canonical_product``
  flag false olduqda ``None`` qaytarır.
- ``channels`` — qoşulu marketplace/delivery/booking platforması. UNIQUE
  ``(tenant_id, code)``.
- ``channel_listings`` — variant ↔ external listing per channel. UNIQUE
  ``(channel_id, variant_id)`` (bir listing per channel); partial UNIQUE
  ``(channel_id, external_listing_id)`` non-NULL (kanal id-ləri unikal).

Hər iki yeni cədvəl tenant_id daşıyır, RLS policy + ``posnet_app`` grant.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_NEW_TABLES = ("channels", "channel_listings")


def upgrade() -> None:
    # --- existing tables: new sync flags ---
    op.add_column(
        "warehouses",
        sa.Column(
            "is_online_sellable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "online_published",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # --- channels ---
    op.create_table(
        "channels",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_channels_tenant_code"),
    )
    op.create_index(op.f("ix_channels_tenant_id"), "channels", ["tenant_id"], unique=False)

    # --- channel_listings ---
    op.create_table(
        "channel_listings",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("channel_id", _UUID, nullable=False),
        sa.Column("variant_id", _UUID, nullable=False),
        sa.Column("external_listing_id", sa.String(length=200), nullable=True),
        sa.Column("external_category", sa.String(length=500), nullable=True),
        sa.Column(
            "external_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "variant_id", name="uq_channel_listings_channel_variant"),
    )
    op.create_index(
        op.f("ix_channel_listings_tenant_id"), "channel_listings", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_channel_listings_channel_id"), "channel_listings", ["channel_id"], unique=False
    )
    op.create_index(
        op.f("ix_channel_listings_variant_id"), "channel_listings", ["variant_id"], unique=False
    )
    # External listing-id channel daxilində unikal (yalnız non-NULL üzərində).
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_listings_channel_external "
        "ON channel_listings (channel_id, external_listing_id) "
        "WHERE external_listing_id IS NOT NULL"
    )

    # --- grants + RLS (yeni cədvəllər) — 0009 FORCE blanket-i dinamik tutur ---
    for table in _NEW_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO posnet_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    op.drop_table("channel_listings")
    op.drop_table("channels")
    op.drop_column("products", "online_published")
    op.drop_column("warehouses", "is_online_sellable")
