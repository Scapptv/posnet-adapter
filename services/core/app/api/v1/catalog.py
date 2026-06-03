"""Catalog API (AI-2.1) — tenant-scoped products, variants, POS lookup.

Reads need ``catalog:read`` (every store role, incl. cashier); writes need
``catalog:write`` (store_manager / clerk / tenant_admin). All run under the
RLS-scoped session, so a tenant only ever sees/edits its own catalog.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import NotFoundError, ValidationError, validate_currency_code

from ...domain.catalog import (
    add_variant,
    create_product,
    find_variant_by_barcode,
    find_variant_by_sku,
    get_product,
    list_products,
)
from ..deps import get_tenant_session, require_tenant, requires_permission

router = APIRouter(tags=["catalog"])
_READ = requires_permission("catalog", "read")
_WRITE = requires_permission("catalog", "write")


# ---- schemas ----


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    currency: str = Field(default="AZN", min_length=3, max_length=3)
    store_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=200)
    category_path: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        return validate_currency_code(value.upper())


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    brand: str | None
    category_path: list[str]
    currency: str
    status: str
    store_id: UUID | None


class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    sort_order: int


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    sku: str
    barcode: str | None
    name: str | None
    attributes: dict[str, str]
    base_price_minor: int
    cost_price_minor: int | None


class ProductDetailResponse(ProductResponse):
    variants: list[VariantResponse]
    images: list[ImageResponse]


class VariantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    base_price_minor: int = Field(ge=0)
    barcode: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    attributes: dict[str, str] = Field(default_factory=dict)
    cost_price_minor: int | None = Field(default=None, ge=0)


# ---- products ----


@router.post("/products", status_code=status.HTTP_201_CREATED, response_model=ProductResponse)
async def create(
    body: ProductCreateRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProductResponse:
    product = await create_product(
        session,
        tenant_id=tenant_id,
        name=body.name,
        currency=body.currency,
        store_id=body.store_id,
        brand=body.brand,
        category_path=body.category_path,
        image_urls=body.image_urls,
    )
    return ProductResponse.model_validate(product)


@router.get("/products", response_model=list[ProductResponse])
async def list_(
    q: str | None = None,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ProductResponse]:
    products = await list_products(session, query=q)
    return [ProductResponse.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
async def detail(
    product_id: UUID,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProductDetailResponse:
    found = await get_product(session, product_id)
    if found is None:
        raise NotFoundError("product not found")
    product, variants, images = found
    return ProductDetailResponse(
        **ProductResponse.model_validate(product).model_dump(),
        variants=[VariantResponse.model_validate(v) for v in variants],
        images=[ImageResponse.model_validate(i) for i in images],
    )


@router.post(
    "/products/{product_id}/variants",
    status_code=status.HTTP_201_CREATED,
    response_model=VariantResponse,
)
async def add_variant_(
    product_id: UUID,
    body: VariantCreateRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> VariantResponse:
    variant = await add_variant(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        sku=body.sku,
        base_price_minor=body.base_price_minor,
        barcode=body.barcode,
        name=body.name,
        attributes=body.attributes,
        cost_price_minor=body.cost_price_minor,
    )
    return VariantResponse.model_validate(variant)


# ---- POS lookup ----


@router.get("/variants/lookup", response_model=VariantResponse)
async def lookup(
    barcode: str | None = None,
    sku: str | None = None,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> VariantResponse:
    if (barcode is None) == (sku is None):
        raise ValidationError("provide exactly one of barcode or sku")
    variant = (
        await find_variant_by_barcode(session, barcode)
        if barcode is not None
        else await find_variant_by_sku(session, sku)  # type: ignore[arg-type]
    )
    if variant is None:
        raise NotFoundError("variant not found")
    return VariantResponse.model_validate(variant)
