"""HTTP mock Posnet FastAPI app (AI-2.8.2).

A real (in-process) stand-in for the Posnet POS over HTTP: ``GET /catalog`` to
pull products/stock/price, ``POST /orders`` to write a channel order back. The
``PosnetConnector`` talks to this exactly as it would to a real Posnet API, so
the mock → real swap is just a base-URL change (ADR-0021). Spin a fresh app per
test via :func:`create_app`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.requests import Request

from .models import CatalogResponse, OrderWrite
from .store import MockPosnetStore


def _store_from_request(request: Request) -> MockPosnetStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[MockPosnetStore, Depends(_store_from_request)]

router = APIRouter()


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(store: StoreDep) -> CatalogResponse:
    return CatalogResponse(products=store.catalog())


@router.post("/orders")
async def write_order(body: OrderWrite, store: StoreDep) -> dict[str, str]:
    store.record_order(body.model_dump())
    return {"status": "recorded", "channel_order_id": body.channel_order_id}


def create_app(store: MockPosnetStore | None = None) -> FastAPI:
    """Build a fresh mock Posnet bound to ``store`` (or a new empty one)."""
    app = FastAPI(title="Mock Posnet", version="0.1.0")
    app.state.store = store or MockPosnetStore()
    app.include_router(router)
    return app
