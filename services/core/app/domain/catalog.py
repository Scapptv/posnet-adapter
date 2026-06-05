"""Tenant-scoped catalog management (AI-2.1 + AI-2.H4 event emit).

Products, their variants (SKU/barcode-centric) and images. Every function runs
under the caller's RLS-scoped session, so reads/writes are confined to the tenant.
Foreign ids supplied by the caller (``store_id``, ``product_id``) are re-checked
with an RLS-scoped SELECT — a FK alone would accept another tenant's id (the FK
check bypasses RLS), so the lookup is what enforces the boundary (cf. AI-1.16
``assign_role``).

Mutations (``create_product`` / ``add_variant``) enqueue a transactional outbox
event after the business write, so the sync engine can project the change onto
external channels (AI-2.H4, audit B1). The event commits with the row.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import ConflictError, NotFoundError
from libs.eventbus import Event, enqueue

from ..infrastructure.db.models import Product, ProductImage, Store, Variant
from .events import CATALOG_PRODUCT_CREATED, CATALOG_VARIANT_ADDED


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
    await enqueue(
        session,
        Event(
            event_type=CATALOG_PRODUCT_CREATED,
            tenant_id=tenant_id,
            payload={
                "product_id": str(product.id),
                "store_id": str(store_id) if store_id is not None else None,
                "name": name,
                "currency": currency,
            },
        ),
    )
    return product


async def set_online_published(
    session: AsyncSession, *, tenant_id: UUID, product_id: UUID, published: bool
) -> Product:
    """Publish / unpublish a product to online channels (AI-2.7).

    Publishing flips the ``online_published`` gate (ADR-0018 §2) and re-emits
    ``catalog.variant.added`` for every variant, so the dispatcher pushes them to
    active channels now that they're eligible. Unpublishing just clears the gate
    (a future delist flow removes the channel listings). RLS-scoped: an unknown /
    cross-tenant id reads as missing."""
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise NotFoundError("product not found in this tenant")
    product.online_published = published
    await session.flush()
    if published:
        variant_ids = (
            (await session.execute(select(Variant.id).where(Variant.product_id == product_id)))
            .scalars()
            .all()
        )
        for variant_id in variant_ids:
            await enqueue(
                session,
                Event(
                    event_type=CATALOG_VARIANT_ADDED,
                    tenant_id=tenant_id,
                    payload={"variant_id": str(variant_id)},
                ),
            )
    await session.refresh(product)
    return product


async def list_products(
    session: AsyncSession,
    *,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> Sequence[Product]:
    """Products (RLS-scoped), optionally full-text filtered by ``query`` on name.

    ``limit``/``offset`` paginate over a deterministic ``ORDER BY name, id`` (the
    ``id`` tiebreaker keeps page boundaries stable when names collide).
    ``limit=None`` returns all matches — callers that page pass an explicit limit.
    """
    stmt = select(Product)
    if query:
        # Matches the gin(to_tsvector('simple', name)) index so it stays index-backed.
        stmt = stmt.where(
            func.to_tsvector("simple", Product.name).op("@@")(func.plainto_tsquery("simple", query))
        )
    stmt = stmt.order_by(Product.name, Product.id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def count_products(session: AsyncSession, *, query: str | None = None) -> int:
    """Total products matching ``query`` (RLS-scoped) — the page total for
    pagination headers, independent of ``limit``/``offset``."""
    stmt = select(func.count()).select_from(Product)
    if query:
        stmt = stmt.where(
            func.to_tsvector("simple", Product.name).op("@@")(func.plainto_tsquery("simple", query))
        )
    return (await session.execute(stmt)).scalar_one()


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
    try:
        # Trips on UNIQUE(tenant_id, sku) or the partial UNIQUE(tenant_id, barcode)
        # WHERE NOT NULL (migration 0010, AI-2.H2). Both shapes resolve to 409.
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "a variant with this sku or barcode already exists in this tenant"
        ) from exc
    await session.refresh(variant)
    await enqueue(
        session,
        Event(
            event_type=CATALOG_VARIANT_ADDED,
            tenant_id=tenant_id,
            payload={
                "product_id": str(product_id),
                "variant_id": str(variant.id),
                "sku": sku,
                "barcode": barcode,
                "base_price_minor": base_price_minor,
            },
        ),
    )
    return variant


async def find_variant_by_barcode(session: AsyncSession, barcode: str) -> Variant | None:
    """POS scan lookup — the (RLS-scoped) variant carrying ``barcode``, if any.

    The tenant-scoped partial UNIQUE on ``(tenant_id, barcode)`` (migration 0010)
    means at most one variant ever matches; the ``ORDER BY id`` is a determinism
    backstop in case the constraint is ever relaxed (audit A2).
    """
    return (
        await session.execute(
            select(Variant).where(Variant.barcode == barcode).order_by(Variant.id).limit(1)
        )
    ).scalar_one_or_none()


async def find_variant_by_sku(session: AsyncSession, sku: str) -> Variant | None:
    """POS scan lookup by SKU. Tenant-scoped UNIQUE(tenant_id, sku) makes this
    deterministic; ``ORDER BY id`` backstops it (audit A2)."""
    return (
        await session.execute(
            select(Variant).where(Variant.sku == sku).order_by(Variant.id).limit(1)
        )
    ).scalar_one_or_none()
