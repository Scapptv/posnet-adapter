"""Identity & Access domain models (AI-1.5, migration 0001).

Every tenant-scoped table carries ``tenant_id`` so RLS (AI-1.6) is uniform:
``USING (tenant_id = current_setting('app.current_tenant')::uuid)``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _fk(table: str) -> ForeignKey:
    return ForeignKey(table, ondelete="CASCADE")


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class Store(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stores"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    open_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'closed'")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Keycloak ``sub`` — globally unique link to the IdP identity. Tenant is
    # resolved per request from this column (ADR-0015); NULL until onboarded.
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Permission(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "resource", "action", name="uq_permissions_role_res_act"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("roles.id"), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)


class UserRole(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "store_id", name="uq_user_roles_user_role_store"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("users.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("roles.id"), nullable=False)
    # NULL store_id = tenant-wide assignment.
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FeatureFlag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-tenant override of a flag declared in the app's ``FlagRegistry`` (AI-1.17).

    A row exists only where a tenant diverges from the built-in default; the
    effective set is the registry defaults overlaid with these rows.
    """

    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_feature_flags_tenant_key"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    meta_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    result_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outbox_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


# ----------------------------------------------------------------------------
# Catalog domain (AI-2.1) — products + variants + images. SKU/barcode-centric so
# it maps cleanly to ``libs.canonical_model.CanonicalProduct`` (the hub, AI-2.6).
# ----------------------------------------------------------------------------


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    # NULL store_id = tenant-wide product; deleting a store leaves its products.
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    # Ordered category names (e.g. ["Food", "Beverages"]); JSONB matches the
    # canonical model's ``category_path`` tuple.
    category_path: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'AZN'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))


class Variant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tenant-scoped SKU/barcode (AI-2.H2, migration 0010).

    Adapter contracts key by SKU, so uniqueness is tenant-wide — a POS scan or a
    channel push resolves to exactly one variant. ``barcode`` uniqueness is
    partial (only the non-NULL ones), so legacy variants without a barcode keep
    coexisting.
    """

    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_variants_tenant_sku"),
        Index(
            "uq_variants_tenant_barcode",
            "tenant_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("products.id"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    base_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_price_minor: Mapped[int | None] = mapped_column(BigInteger)


class ProductImage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "product_images"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("products.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


# ----------------------------------------------------------------------------
# Inventory domain (AI-2.2) — per-(variant, warehouse) stock levels with an
# append-only movement journal. ``available = qty - reserved_qty``; reservations
# are the anti-oversell mechanism (a sale across channels reserves before it ships).
# ----------------------------------------------------------------------------


class Warehouse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "warehouses"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'store'"))


class Inventory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inventory"
    # DB-level anti-oversell backstop (AI-2.H2, migration 0010). The domain
    # ``_effect`` guard catches violations first; these CHECKs close the gap if
    # any future code path skips it.
    __table_args__ = (
        UniqueConstraint("variant_id", "warehouse_id", name="uq_inventory_variant_warehouse"),
        CheckConstraint("qty >= 0", name="ck_inventory_qty_nonneg"),
        CheckConstraint("reserved_qty >= 0", name="ck_inventory_reserved_nonneg"),
        CheckConstraint("reserved_qty <= qty", name="ck_inventory_reserved_le_qty"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("variants.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("warehouses.id"), nullable=False
    )
    qty: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    reserved_qty: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    min_qty: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    # Optimistic-lock counter, bumped on every movement (clients may pass it back to
    # detect a stale write; the row is also SELECT ... FOR UPDATE-locked per movement).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class StockMovement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "stock_movements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("variants.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("warehouses.id"), nullable=False
    )
    # in | out | reserve | unreserve | adjust (roadmap §16 "type")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    moved_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False, index=True
    )


# ----------------------------------------------------------------------------
# Pricing domain (AI-2.3) — the effective sell price is the variant's
# ``base_price_minor`` unless a (store/time-scoped) override applies. The full
# rule engine (percent/tiered) lands later; this is the "optional rule" overlay.
# ----------------------------------------------------------------------------


class PriceOverride(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "price_overrides"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("variants.id"), nullable=False, index=True
    )
    # NULL store_id = applies to every store; a store-specific override wins over it.
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE")
    )
    price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Optional validity window (NULL = open-ended); an override applies only while active.
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


# ----------------------------------------------------------------------------
# Sales — shift/vardiya (AI-2.4). A cashier opens a till (opening cash), records
# cash pay-in/out during the shift, then closes it (closing cash). Sales (AI-2.5)
# attach to the open shift. At most one open shift per (store, cashier).
# ----------------------------------------------------------------------------


class Shift(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "shifts"
    __table_args__ = (
        Index(
            "uq_shifts_open",
            "store_id",
            "cashier_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("stores.id"), nullable=False, index=True
    )
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'open'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'AZN'"))
    opening_cash_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closing_cash_minor: Mapped[int | None] = mapped_column(BigInteger)
    opened_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class CashMovement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cash_movements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("tenants.id"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("shifts.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # in | out
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
