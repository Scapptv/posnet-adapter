"""AI-2.2 — inventory movement logic + request schemas (unit, no IO)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from libs.common import ConflictError, ValidationError
from services.core.app.api.v1.inventory import MovementRequest, WarehouseCreateRequest
from services.core.app.domain.inventory import _effect

_VARIANT = "11111111-1111-1111-1111-111111111111"
_WAREHOUSE = "22222222-2222-2222-2222-222222222222"


# ---- _effect (anti-oversell core) ----


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "qty", "on_hand", "reserved", "expected"),
    [
        ("in", 10, 0, 0, (10, 0)),
        ("out", 3, 10, 2, (7, 2)),  # available 8 >= 3
        ("reserve", 5, 10, 2, (10, 7)),  # available 8 >= 5
        ("unreserve", 2, 10, 5, (10, 3)),
        ("adjust", -4, 10, 2, (6, 2)),  # signed down, still >= reserved
        ("adjust", 5, 10, 2, (15, 2)),
    ],
)
def test_effect_happy(
    kind: str, qty: int, on_hand: int, reserved: int, expected: tuple[int, int]
) -> None:
    assert _effect(kind, qty, on_hand, reserved) == expected


@pytest.mark.unit
def test_effect_out_beyond_available_conflicts() -> None:
    with pytest.raises(ConflictError):
        _effect("out", 9, 10, 2)  # available 8 < 9


@pytest.mark.unit
def test_effect_reserve_beyond_available_conflicts() -> None:
    with pytest.raises(ConflictError):
        _effect("reserve", 9, 10, 2)  # anti-oversell: available 8 < 9


@pytest.mark.unit
def test_effect_unreserve_more_than_reserved() -> None:
    with pytest.raises(ValidationError):
        _effect("unreserve", 6, 10, 5)


@pytest.mark.unit
def test_effect_adjust_below_reserved() -> None:
    with pytest.raises(ValidationError):
        _effect("adjust", -9, 10, 2)  # new qty 1 < reserved 2


# ---- request schemas ----


@pytest.mark.unit
def test_warehouse_request_defaults_type() -> None:
    assert WarehouseCreateRequest(name="Main").type == "store"


@pytest.mark.unit
def test_movement_request_accepts_adjust_negative() -> None:
    req = MovementRequest(variant_id=_VARIANT, warehouse_id=_WAREHOUSE, kind="adjust", qty=-3)
    assert req.qty == -3


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "teleport", "qty": 1},  # unknown kind
        {"kind": "in", "qty": 0},  # positive kind needs qty > 0
        {"kind": "reserve", "qty": -2},  # negative for non-adjust
        {"kind": "adjust", "qty": 0},  # adjust must be non-zero
        {"kind": "in", "qty": 1, "extra": "x"},  # extra forbidden
    ],
    ids=["unknown-kind", "in-zero", "reserve-negative", "adjust-zero", "extra-field"],
)
def test_movement_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(PydanticValidationError):
        MovementRequest(variant_id=_VARIANT, warehouse_id=_WAREHOUSE, **overrides)
