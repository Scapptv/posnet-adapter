"""Tenant-scoped catalog management (AI-2.1).

Products, their variants (SKU/barcode-centric) and images. Every function runs
under the caller's RLS-scoped session, so reads/writes are confined to the tenant.
Foreign ids supplied by the caller (``store_id``, ``product_id``) are re-checked
with an RLS-scoped SELECT — a FK alone would accept another tenant's id (the FK
check bypasses RLS), so the lookup is what enforces the boundary (cf. AI-1.16
``assign_role``).

No outbox events yet — the sync engine that consumes catalog changes lands with
the adapter framework (AI-2.5); this phase is the source-of-truth CRUD.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import NotFoundError

from ..infrastructure.db.models import Product, ProductImage, Store, Variant


async def create_product(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    currency: str,
    store_id: UUID | None = None,
    brand: str | None = None,
    category_path: Sequence[str] = (),
    image_urls: Sequence[str] = (),
) -> Product:
    if store_id is not None:
        store = (await session.execute(select(Store.id).where(Store.id == store_id))).first()
        if store is None:
            raise NotFoundError("store not found in this tenant")

    product = Product(
        tenant_id=tenant_id,
        store_id=store_id,
        name=name,
        brand=brand,
        category_path=list(category_path),
        currency=currency,
    )
    session.add(product)
    await session.flush()  # assigns product.id
    for order, url in enumerate(image_urls):
        session.add(
            ProductImage(tenant_id=tenant_id, product_id=product.id, url=url, sort_order=order)
        )
    await session.flush()
    await session.refresh(product)
    return product


async def list_products(session: AsyncSession, *, query: str | None = None) -> Sequence[Product]:
    """All products (RLS-scoped), optionally full-text filtered by ``query`` on name."""
    stmt = select(Product)
    if query:
        # Matches the gin(to_tsvector('simple', name)) index so it stays index-backed.
        stmt = stmt.where(
            func.to_tsvector("simple", Product.name).op("@@")(func.plainto_tsquery("simple", query))
        )
    return (await session.execute(stmt.order_by(Product.name))).scalars().all()


async def get_product(
    session: AsyncSession, product_id: UUID
) -> tuple[Product, list[Variant], list[ProductImage]] | None:
    """A product with its variants + images, or ``None`` if not in this tenant."""
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        return None
    variants = list(
        (
            await session.execute(
                select(Variant).where(Variant.product_id == product_id).order_by(Variant.sku)
            )
        )
        .scalars()
        .all()
    )
    images = list(
        (
            await session.execute(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order)
            )
        )
        .scalars()
        .all()
    )
    return product, variants, images


async def add_variant(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    product_id: UUID,
    sku: str,
    base_price_minor: int,
    barcode: str | None = None,
    name: str | None = None,
    attributes: dict[str, str] | None = None,
    cost_price_minor: int | None = None,
) -> Variant:
    product = (await session.execute(select(Product.id).where(Product.id == product_id))).first()
    if product is None:
        raise NotFoundError("product not found in this tenant")

    variant = Variant(
        tenant_id=tenant_id,
        product_id=product_id,
        sku=sku,
        barcode=barcode,
        name=name,
        attributes=attributes or {},
        base_price_minor=base_price_minor,
        cost_price_minor=cost_price_minor,
    )
    session.add(variant)
    await session.flush()  # raises IntegrityError on duplicate (product_id, sku)
    await session.refresh(variant)
    return variant


async def find_variant_by_barcode(session: AsyncSession, barcode: str) -> Variant | None:
    """POS scan lookup — the (RLS-scoped) variant carrying ``barcode``, if any."""
    return (
        await session.execute(select(Variant).where(Variant.barcode == barcode).limit(1))
    ).scalar_one_or_none()


async def find_variant_by_sku(session: AsyncSession, sku: str) -> Variant | None:
    return (
        await session.execute(select(Variant).where(Variant.sku == sku).limit(1))
    ).scalar_one_or_none()
