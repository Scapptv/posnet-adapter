"""Shift/vardiya API (AI-2.4) — open/close a till + cash management.

``shift:read``/``shift:write`` (cashier + store_manager). A cashier opens a shift
with an opening float, records pay-in/out, and closes it with the counted cash;
the detail view reports the expected drawer position (pre-sales).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from libs.auth import Principal
from libs.common import NotFoundError, validate_currency_code

from ...domain.shift import (
    CASH_KINDS,
    cash_summary,
    close_shift,
    get_shift,
    list_shifts,
    open_shift,
    record_cash,
)
from ..deps import get_tenant_session, require_tenant, requires_permission

router = APIRouter(prefix="/shifts", tags=["shifts"])
_READ = requires_permission("shift", "read")
_WRITE = requires_permission("shift", "write")


# ---- schemas ----


class OpenShiftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    cashier_id: UUID
    opening_cash_minor: int = Field(ge=0)
    currency: str = Field(default="AZN", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        return validate_currency_code(value.upper())


class CloseShiftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closing_cash_minor: int = Field(ge=0)


class CashMovementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    amount_minor: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        if value not in CASH_KINDS:
            raise ValueError(f"kind must be one of {sorted(CASH_KINDS)}")
        return value


class ShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    cashier_id: UUID
    status: str
    currency: str
    opening_cash_minor: int
    closing_cash_minor: int | None
    opened_at: datetime
    closed_at: datetime | None


class ShiftDetailResponse(ShiftResponse):
    cash_in_minor: int
    cash_out_minor: int
    expected_cash_minor: int


class CashMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shift_id: UUID
    kind: str
    amount_minor: int
    reason: str | None


# ---- endpoints ----


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ShiftResponse)
async def open_(
    body: OpenShiftRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ShiftResponse:
    shift = await open_shift(
        session,
        tenant_id=tenant_id,
        store_id=body.store_id,
        cashier_id=body.cashier_id,
        opening_cash_minor=body.opening_cash_minor,
        currency=body.currency,
    )
    return ShiftResponse.model_validate(shift)


@router.get("", response_model=list[ShiftResponse])
async def list_(
    store_id: UUID | None = None,
    status_: str | None = None,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ShiftResponse]:
    shifts = await list_shifts(session, store_id=store_id, status=status_)
    return [ShiftResponse.model_validate(s) for s in shifts]


@router.get("/{shift_id}", response_model=ShiftDetailResponse)
async def detail(
    shift_id: UUID,
    _r: Principal = Depends(_READ),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ShiftDetailResponse:
    shift = await get_shift(session, shift_id)
    if shift is None:
        raise NotFoundError("shift not found")
    summary = await cash_summary(session, shift)
    return ShiftDetailResponse(
        **ShiftResponse.model_validate(shift).model_dump(),
        cash_in_minor=summary.cash_in_minor,
        cash_out_minor=summary.cash_out_minor,
        expected_cash_minor=summary.expected_cash_minor,
    )


@router.post("/{shift_id}/close", response_model=ShiftResponse)
async def close_(
    shift_id: UUID,
    body: CloseShiftRequest,
    _w: Principal = Depends(_WRITE),
    _tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> ShiftResponse:
    shift = await close_shift(
        session, shift_id=shift_id, closing_cash_minor=body.closing_cash_minor
    )
    return ShiftResponse.model_validate(shift)


@router.post(
    "/{shift_id}/cash-movements",
    status_code=status.HTTP_201_CREATED,
    response_model=CashMovementResponse,
)
async def cash(
    shift_id: UUID,
    body: CashMovementRequest,
    _w: Principal = Depends(_WRITE),
    tenant_id: UUID = Depends(require_tenant),
    session: AsyncSession = Depends(get_tenant_session),
) -> CashMovementResponse:
    movement = await record_cash(
        session,
        tenant_id=tenant_id,
        shift_id=shift_id,
        kind=body.kind,
        amount_minor=body.amount_minor,
        reason=body.reason,
    )
    return CashMovementResponse.model_validate(movement)
