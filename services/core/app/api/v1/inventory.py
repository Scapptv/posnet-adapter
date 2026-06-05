"""Inventory API (AI-2.2) — warehouses, stock movements, levels.

Reads need ``inventory:read`` (store roles incl. cashier); writes need
``inventory:write`` (store_manager / clerk / tenant_admin). The movement endpoint
is the single write path: it serialises on the inventory row and enforces
anti-oversell, so reservations/sales can never promise the same unit twice.
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal

from ...domain.inventory import (
    MOVEMENT_KINDS,
    apply_movement,
    create_warehouse,
    get_inventory,
    list_warehouses,
    transfer_stock,
)
from ..deps import get_tenant_session, require_tenant, requires_permission

router = APIRouter(tags=["inventory"])
_READ = requires_permission("inventory", "read")
_WRITE = requires_permission("inventory", "write")


# ---- schemas ----


class WarehouseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    type: str = Field(default="store", min_length=1, max_length=20)


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: str


class MovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: UUID
    warehouse_id: UUID
    kind: str
    qty: int
    reference: str | None = Field(default=None, max_length=200)
    expected_version: int | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in MOVEMENT_KINDS:
            raise ValueError(f"kind must be one of {sorted(MOVEMENT_KINDS)}")
        return value

    @model_validator(mode="after")
    def _qty_sign(self) -> Self:
        # ``adjust`` is a signed correction; every other kind is a positive quantity.
        if self.kind == "adjust":
            if self.qty == 0:
                raise ValueError("adjust qty must be non-zero")
        elif self.qty <= 0:
            raise ValueError(f"{self.kind} qty must be positive")
        return self


class InventoryLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    warehouse_id: UUID
    qty: int
    reserved_qty: int
    min_qty: int
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> int:
        return self.qty - self.reserved_qty


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: UUID
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    qty: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=200)


class TransferResponse(BaseModel):
    """Both legs of an atomic transfer — source debited, destination credited."""

    source: InventoryLevelResponse
    destination: InventoryLevelResponse


# ---- warehouses ----


@router.post("/warehouses", status_code=status.HTTP_201_CREATED, response_model=WarehouseResponse)
async def create_warehouse_(
    body: WarehouseCreateRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> WarehouseResponse:
    warehouse = await create_warehouse(
        session, tenant_id=tenant_id, name=body.name, type_=body.type
    )
    return WarehouseResponse.model_validate(warehouse)


@router.get("/warehouses", response_model=list[WarehouseResponse])
async def list_warehouses_(
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[WarehouseResponse]:
    return [WarehouseResponse.model_validate(w) for w in await list_warehouses(session)]


# ---- movements + levels ----


@router.post(
    "/inventory/movements",
    status_code=status.HTTP_201_CREATED,
    response_model=InventoryLevelResponse,
)
async def move(
    body: MovementRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> InventoryLevelResponse:
    level = await apply_movement(
        session,
        tenant_id=tenant_id,
        variant_id=body.variant_id,
        warehouse_id=body.warehouse_id,
        kind=body.kind,
        qty=body.qty,
        reference=body.reference,
        expected_version=body.expected_version,
    )
    return InventoryLevelResponse.model_validate(level)


@router.post(
    "/inventory/transfers",
    status_code=status.HTTP_201_CREATED,
    response_model=TransferResponse,
)
async def transfer(
    body: TransferRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> TransferResponse:
    source, destination = await transfer_stock(
        session,
        tenant_id=tenant_id,
        variant_id=body.variant_id,
        from_warehouse_id=body.from_warehouse_id,
        to_warehouse_id=body.to_warehouse_id,
        qty=body.qty,
        reference=body.reference,
    )
    return TransferResponse(
        source=InventoryLevelResponse.model_validate(source),
        destination=InventoryLevelResponse.model_validate(destination),
    )


@router.get("/inventory", response_model=list[InventoryLevelResponse])
async def levels(
    variant_id: UUID,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[InventoryLevelResponse]:
    return [
        InventoryLevelResponse.model_validate(i) for i in await get_inventory(session, variant_id)
    ]
