"""Mock Bazar (2nd marketplace) FastAPI app (Part V V1.1).

Same capability set as mock-marketplace, deliberately different HTTP surface
(``/products`` + ``PUT`` verbs + ``/sales`` + ``from`` query) so the 2nd adapter
exercises a genuinely different wire contract. Fresh store per ``create_app``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.requests import Request

from .models import (
    PriceUpdate,
    ProductRef,
    ProductUpsert,
    ProductView,
    QuantityUpdate,
    Sale,
    SaleSeedRequest,
    SalesPage,
    StateUpdate,
)
from .store import MockBazarStore


def _store_from_request(request: Request) -> MockBazarStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[MockBazarStore, Depends(_store_from_request)]

router = APIRouter()


def _ref(product: object) -> ProductRef:
    return ProductRef(
        ref=product.ref,  # type: ignore[attr-defined]
        merchant_sku=product.merchant_sku,  # type: ignore[attr-defined]
        state=product.state,  # type: ignore[attr-defined]
    )


# -------- products --------


@router.post("/products", status_code=status.HTTP_201_CREATED, response_model=ProductRef)
async def upsert_product(body: ProductUpsert, store: StoreDep) -> ProductRef:
    product = store.upsert_product(
        merchant_sku=body.merchant_sku,
        gtin=body.gtin,
        title=body.title,
        attrs=body.attrs,
        category_path=body.category_path,
        amount_minor=body.price.amount_minor,
        currency=body.price.currency,
        quantity=body.quantity,
    )
    return _ref(product)


@router.put("/products/{merchant_sku}/quantity", response_model=ProductRef)
async def update_quantity(merchant_sku: str, body: QuantityUpdate, store: StoreDep) -> ProductRef:
    product = store.set_quantity(merchant_sku=merchant_sku, quantity=body.quantity)
    if product is None:
        raise HTTPException(status_code=404, detail="unknown merchant_sku")
    return _ref(product)


@router.put("/products/{merchant_sku}/price", response_model=ProductRef)
async def update_price(merchant_sku: str, body: PriceUpdate, store: StoreDep) -> ProductRef:
    product = store.set_price(
        merchant_sku=merchant_sku,
        amount_minor=body.price.amount_minor,
        currency=body.price.currency,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="unknown merchant_sku")
    return _ref(product)


@router.get("/products/{merchant_sku}", response_model=ProductView)
async def get_product(merchant_sku: str, store: StoreDep) -> ProductView:
    product = store.product_by_sku(merchant_sku)
    if product is None:
        raise HTTPException(status_code=404, detail="unknown merchant_sku")
    return ProductView(
        ref=product.ref,
        merchant_sku=product.merchant_sku,
        state=product.state,  # type: ignore[arg-type]
        quantity=product.quantity,
        price={"amount_minor": product.amount_minor, "currency": product.currency},  # type: ignore[arg-type]
    )


# -------- sales --------


@router.get("/sales", response_model=SalesPage)
async def list_sales(store: StoreDep, from_: Annotated[datetime, Query(alias="from")]) -> SalesPage:
    return SalesPage(sales=store.sales_since(from_))


@router.post("/sales/{ref}/state")
async def set_sale_state(ref: str, body: StateUpdate, store: StoreDep) -> dict[str, str]:
    if not store.set_sale_state(ref=ref, state=body.state):
        raise HTTPException(status_code=404, detail="unknown sale ref")
    return {"ref": ref, "state": body.state}


# -------- test hooks (not the real Bazar API) --------


@router.post("/_test/sales", status_code=status.HTTP_201_CREATED, response_model=Sale)
async def seed_sale(body: SaleSeedRequest, store: StoreDep) -> Sale:
    return store.seed_sale(items=body.items, currency=body.currency, buyer_name=body.buyer_name)


def create_app(store: MockBazarStore | None = None) -> FastAPI:
    """Build a fresh Mock Bazar bound to ``store`` (or a new empty one)."""
    app = FastAPI(title="Mock Bazar", version="0.1.0")
    app.state.store = store or MockBazarStore()
    app.include_router(router)
    return app
