"""Mock marketplace FastAPI app (AI-2.5.3).

Spin a fresh instance with :func:`create_app` — each one owns its
:class:`MockStore`, so tests don't share state. The real partner Birmarket /
Trendyol API will land at the same surface in AI-2.5+.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.requests import Request

from .models import (
    AcknowledgeRequest,
    ListingCreate,
    ListingResponse,
    OrderDTO,
    OrderSeedRequest,
    OrdersPage,
    PriceUpdate,
    StockUpdate,
)
from .store import MockStore


def _store_from_request(request: Request) -> MockStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[MockStore, Depends(_store_from_request)]
"""Module-level dep so FastAPI's ``get_type_hints`` can resolve it on
route functions (closure-local aliases don't survive introspection)."""


router = APIRouter()


# -------- listings --------


@router.post("/listings", status_code=status.HTTP_201_CREATED, response_model=ListingResponse)
async def create_listing(body: ListingCreate, store: StoreDep) -> ListingResponse:
    listing = store.upsert_listing(
        seller_sku=body.seller_sku,
        barcode=body.barcode,
        name=body.name,
        attributes=body.attributes,
        category=body.category,
        price_minor=body.price_minor,
        currency=body.currency,
        stock=body.stock,
    )
    return ListingResponse(
        external_listing_id=listing.external_id,
        seller_sku=listing.seller_sku,
        status=listing.status,  # type: ignore[arg-type]
    )


@router.patch("/listings/{seller_sku}/stock", response_model=ListingResponse)
async def update_stock(seller_sku: str, body: StockUpdate, store: StoreDep) -> ListingResponse:
    listing = store.set_stock(seller_sku=seller_sku, qty=body.qty)
    if listing is None:
        raise HTTPException(status_code=404, detail="unknown seller_sku")
    return ListingResponse(
        external_listing_id=listing.external_id,
        seller_sku=listing.seller_sku,
        status=listing.status,  # type: ignore[arg-type]
    )


@router.patch("/listings/{seller_sku}/price", response_model=ListingResponse)
async def update_price(seller_sku: str, body: PriceUpdate, store: StoreDep) -> ListingResponse:
    listing = store.set_price(
        seller_sku=seller_sku, price_minor=body.price_minor, currency=body.currency
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="unknown seller_sku")
    return ListingResponse(
        external_listing_id=listing.external_id,
        seller_sku=listing.seller_sku,
        status=listing.status,  # type: ignore[arg-type]
    )


# -------- orders --------


@router.get("/orders", response_model=OrdersPage)
async def list_orders(
    store: StoreDep,
    since: Annotated[datetime, Query()],
) -> OrdersPage:
    return OrdersPage(orders=store.orders_since(since))


@router.post("/orders/{channel_order_id}/ack")
async def acknowledge_order(
    channel_order_id: str, body: AcknowledgeRequest, store: StoreDep
) -> dict[str, str]:
    ok = store.acknowledge(channel_order_id=channel_order_id, status=body.status)
    if not ok:
        raise HTTPException(status_code=404, detail="unknown channel_order_id")
    return {"channel_order_id": channel_order_id, "status": body.status}


# -------- test hooks (not part of the real channel API) --------


@router.post("/_test/orders", status_code=status.HTTP_201_CREATED, response_model=OrderDTO)
async def seed_order(body: OrderSeedRequest, store: StoreDep) -> OrderDTO:
    return store.seed_order(
        lines=body.lines, currency=body.currency, customer_name=body.customer_name
    )


def create_app(store: MockStore | None = None) -> FastAPI:
    """Build a fresh mock marketplace bound to ``store`` (or a new empty one)."""
    app = FastAPI(title="Mock Marketplace", version="0.1.0")
    app.state.store = store or MockStore()
    app.include_router(router)
    return app
