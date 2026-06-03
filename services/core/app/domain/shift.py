"""Tenant-scoped shifts/vardiya + cash management (AI-2.4).

A cashier opens a till with an opening float, records cash pay-in/out during the
shift, then closes it with the counted closing cash. The DB enforces at most one
*open* shift per (store, cashier) via a partial unique index; the domain maps that
to a conflict. Sales (AI-2.5) attach to the open shift. ``expected_cash`` is the
pre-sales drawer position (opening + pay-ins - pay-outs).

Foreign ids (store, cashier, shift) are re-checked under RLS so a cross-tenant id
reads as missing rather than being accepted by the FK alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import ConflictError, NotFoundError, ValidationError

from ..infrastructure.db.models import CashMovement, Shift, Store, User

CASH_KINDS = frozenset({"in", "out"})


@dataclass(frozen=True)
class CashSummary:
    opening_cash_minor: int
    cash_in_minor: int
    cash_out_minor: int
    expected_cash_minor: int


async def open_shift(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    store_id: UUID,
    cashier_id: UUID,
    opening_cash_minor: int,
    currency: str,
) -> Shift:
    if (await session.execute(select(Store.id).where(Store.id == store_id))).first() is None:
        raise NotFoundError("store not found in this tenant")
    if (await session.execute(select(User.id).where(User.id == cashier_id))).first() is None:
        raise NotFoundError("cashier not found in this tenant")

    shift = Shift(
        tenant_id=tenant_id,
        store_id=store_id,
        cashier_id=cashier_id,
        opening_cash_minor=opening_cash_minor,
        currency=currency,
    )
    session.add(shift)
    try:
        await session.flush()  # partial-unique index rejects a second open shift
    except IntegrityError as exc:
        raise ConflictError("a shift is already open for this cashier in this store") from exc
    await session.refresh(shift)
    return shift


async def close_shift(session: AsyncSession, *, shift_id: UUID, closing_cash_minor: int) -> Shift:
    shift = (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one_or_none()
    if shift is None:
        raise NotFoundError("shift not found in this tenant")
    if shift.status != "open":
        raise ConflictError("shift is already closed")
    shift.status = "closed"
    shift.closing_cash_minor = closing_cash_minor
    shift.closed_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(shift)
    return shift


async def record_cash(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    shift_id: UUID,
    kind: str,
    amount_minor: int,
    reason: str | None = None,
) -> CashMovement:
    status = (
        await session.execute(select(Shift.status).where(Shift.id == shift_id))
    ).scalar_one_or_none()
    if status is None:
        raise NotFoundError("shift not found in this tenant")
    if status != "open":
        raise ValidationError("cannot record cash on a closed shift")

    movement = CashMovement(
        tenant_id=tenant_id, shift_id=shift_id, kind=kind, amount_minor=amount_minor, reason=reason
    )
    session.add(movement)
    await session.flush()
    await session.refresh(movement)
    return movement


async def get_shift(session: AsyncSession, shift_id: UUID) -> Shift | None:
    return (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one_or_none()


async def list_shifts(
    session: AsyncSession, *, store_id: UUID | None = None, status: str | None = None
) -> Sequence[Shift]:
    stmt = select(Shift)
    if store_id is not None:
        stmt = stmt.where(Shift.store_id == store_id)
    if status is not None:
        stmt = stmt.where(Shift.status == status)
    return (await session.execute(stmt.order_by(Shift.opened_at.desc()))).scalars().all()


async def cash_summary(session: AsyncSession, shift: Shift) -> CashSummary:
    rows = (
        (
            await session.execute(
                select(CashMovement.kind, func.coalesce(func.sum(CashMovement.amount_minor), 0))
                .where(CashMovement.shift_id == shift.id)
                .group_by(CashMovement.kind)
            )
        )
        .tuples()
        .all()
    )
    totals = {kind: int(total) for kind, total in rows}
    cash_in = totals.get("in", 0)
    cash_out = totals.get("out", 0)
    return CashSummary(
        opening_cash_minor=shift.opening_cash_minor,
        cash_in_minor=cash_in,
        cash_out_minor=cash_out,
        expected_cash_minor=shift.opening_cash_minor + cash_in - cash_out,
    )
