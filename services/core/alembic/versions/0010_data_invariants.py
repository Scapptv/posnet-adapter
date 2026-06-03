"""data identity & invariant: tenant-scoped SKU/barcode + stock CHECK + journal lockdown (AI-2.H2)

Audit A2/A3/A4 fixes (ADR-0016):

- ``UNIQUE(tenant_id, sku)`` on ``variants`` — adapter contracts (Trendyol /
  Birmarket / Wolt) all key by SKU; the old ``UNIQUE(product_id, sku)`` allowed
  the same SKU across two products in the same tenant, so a POS scan could
  resolve to either at random. Tenant-scoped uniqueness makes the lookup
  deterministic.
- ``UNIQUE(tenant_id, barcode) WHERE barcode IS NOT NULL`` — same reasoning for
  POS barcode scans. Partial so a variant without a barcode does not collide
  with any other variant without a barcode.
- ``CHECK (qty >= 0 AND reserved_qty >= 0 AND reserved_qty <= qty)`` on
  ``inventory`` — DB-level anti-oversell backstop. The domain ``_effect`` guard
  catches it first; the CHECK closes the gap if a future code path skips the
  guard.
- Journal lock-down: ``stock_movements``, ``cash_movements`` and ``audit_logs``
  are append-only by design. Revoke ``UPDATE`` and ``DELETE`` from ``posnet_app``
  so a compromised app session cannot rewrite history. Cascade deletes still
  work — FK cascade actions run with the table owner's privileges, not the
  caller's.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "posnet_app"
_JOURNAL_TABLES = ("stock_movements", "cash_movements", "audit_logs")


def upgrade() -> None:
    # --- variants: tenant-scoped identity (audit A2) ---
    # Drop the per-product uniqueness — the tenant-wide one subsumes it (a tenant
    # may not reuse the same SKU across products either).
    op.drop_constraint("uq_variants_product_sku", "variants", type_="unique")
    op.create_unique_constraint("uq_variants_tenant_sku", "variants", ["tenant_id", "sku"])
    # Partial unique so multiple barcode-less variants coexist; a non-NULL
    # barcode is unique within the tenant.
    op.execute(
        "CREATE UNIQUE INDEX uq_variants_tenant_barcode ON variants (tenant_id, barcode) "
        "WHERE barcode IS NOT NULL"
    )

    # --- inventory: DB-level anti-oversell backstop (audit A4) ---
    op.create_check_constraint(
        "ck_inventory_qty_nonneg",
        "inventory",
        "qty >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_reserved_nonneg",
        "inventory",
        "reserved_qty >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_reserved_le_qty",
        "inventory",
        "reserved_qty <= qty",
    )

    # --- journal tables: append-only (audit A3 / schema) ---
    for table in _JOURNAL_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {APP_ROLE}")


def downgrade() -> None:
    for table in _JOURNAL_TABLES:
        op.execute(f"GRANT UPDATE, DELETE ON {table} TO {APP_ROLE}")

    op.drop_constraint("ck_inventory_reserved_le_qty", "inventory", type_="check")
    op.drop_constraint("ck_inventory_reserved_nonneg", "inventory", type_="check")
    op.drop_constraint("ck_inventory_qty_nonneg", "inventory", type_="check")

    op.execute("DROP INDEX IF EXISTS uq_variants_tenant_barcode")
    op.drop_constraint("uq_variants_tenant_sku", "variants", type_="unique")
    op.create_unique_constraint("uq_variants_product_sku", "variants", ["product_id", "sku"])
