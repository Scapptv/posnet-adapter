"""AI-2.H3 — anti-oversell property tests for ``_effect`` (audit A4/A5).

The domain ``_effect`` function is the entire correctness story for inventory:
every movement type funnels through it, and what it guarantees is the
inventory invariant — ``qty >= 0``, ``reserved_qty >= 0``,
``reserved_qty <= qty``. These tests use Hypothesis to drive that invariant
across thousands of randomly-generated states, instead of just the handful of
example values picked in the integration suite.

The DB ``CHECK`` constraints from migration 0010 are the second line of
defence; ``_effect`` proven safe here means a movement that returns *cannot*
violate the DB CHECK, so the integration suite never has to exercise that
fall-back to confirm anti-oversell.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from libs.common import ConflictError, ValidationError
from services.core.app.domain.inventory import _effect

# Real inventory values are 64-bit BigInteger; cap the range so the test stays
# fast and arithmetic never overflows Python's int (which is arbitrary-precision
# anyway, but the DB column is bounded).
_BIG = 10**12


# A valid pre-state: matches the DB CHECK constraints from migration 0010.
@st.composite
def _valid_state(draw: st.DrawFn) -> tuple[int, int]:
    qty = draw(st.integers(min_value=0, max_value=_BIG))
    reserved = draw(st.integers(min_value=0, max_value=qty))
    return qty, reserved


_POSITIVE = st.integers(min_value=1, max_value=_BIG)
_ANY_DELTA = st.integers(min_value=-_BIG, max_value=_BIG).filter(lambda x: x != 0)


# ----------------------------------------------------------------------------
# Core invariant — every successful call lands in a CHECK-valid state.
# ----------------------------------------------------------------------------


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_effect_in_preserves_invariant(state: tuple[int, int], qty: int) -> None:
    """``in`` always succeeds for positive qty and leaves the row valid."""
    on_hand, reserved = state
    new_qty, new_reserved = _effect("in", qty, on_hand, reserved)
    assert new_qty == on_hand + qty
    assert new_reserved == reserved
    _assert_invariant(new_qty, new_reserved)


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_effect_out_either_raises_or_preserves_invariant(state: tuple[int, int], qty: int) -> None:
    """``out`` raises ConflictError when it would oversell; otherwise the row
    stays valid and ``reserved`` is untouched."""
    on_hand, reserved = state
    available = on_hand - reserved
    if qty > available:
        with pytest.raises(ConflictError):
            _effect("out", qty, on_hand, reserved)
    else:
        new_qty, new_reserved = _effect("out", qty, on_hand, reserved)
        assert new_qty == on_hand - qty
        assert new_reserved == reserved
        _assert_invariant(new_qty, new_reserved)


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_effect_reserve_either_raises_or_preserves_invariant(
    state: tuple[int, int], qty: int
) -> None:
    """``reserve`` raises ConflictError when it would oversell; otherwise the
    row stays valid and ``qty`` is untouched."""
    on_hand, reserved = state
    available = on_hand - reserved
    if qty > available:
        with pytest.raises(ConflictError):
            _effect("reserve", qty, on_hand, reserved)
    else:
        new_qty, new_reserved = _effect("reserve", qty, on_hand, reserved)
        assert new_qty == on_hand
        assert new_reserved == reserved + qty
        _assert_invariant(new_qty, new_reserved)


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_effect_unreserve_either_raises_or_preserves_invariant(
    state: tuple[int, int], qty: int
) -> None:
    """``unreserve`` rejects releasing more than is reserved; otherwise the row
    stays valid."""
    on_hand, reserved = state
    if qty > reserved:
        with pytest.raises(ValidationError):
            _effect("unreserve", qty, on_hand, reserved)
    else:
        new_qty, new_reserved = _effect("unreserve", qty, on_hand, reserved)
        assert new_qty == on_hand
        assert new_reserved == reserved - qty
        _assert_invariant(new_qty, new_reserved)


@pytest.mark.unit
@given(state=_valid_state(), delta=_ANY_DELTA)
def test_effect_adjust_either_raises_or_preserves_invariant(
    state: tuple[int, int], delta: int
) -> None:
    """``adjust`` is a signed delta. It rejects any change that would push
    ``qty`` below zero or below ``reserved``."""
    on_hand, reserved = state
    new_qty_candidate = on_hand + delta
    if new_qty_candidate < reserved:
        with pytest.raises(ValidationError):
            _effect("adjust", delta, on_hand, reserved)
    else:
        new_qty, new_reserved = _effect("adjust", delta, on_hand, reserved)
        assert new_qty == new_qty_candidate
        assert new_reserved == reserved
        _assert_invariant(new_qty, new_reserved)


# ----------------------------------------------------------------------------
# Algebraic round-trips — what one movement type does, its opposite undoes.
# ----------------------------------------------------------------------------


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_in_then_out_returns_to_start(state: tuple[int, int], qty: int) -> None:
    """Receive N then ship N — the level returns to the starting point. (Anti-
    oversell still holds: we just shipped what we received.)"""
    on_hand, reserved = state
    after_in_qty, after_in_reserved = _effect("in", qty, on_hand, reserved)
    final_qty, final_reserved = _effect("out", qty, after_in_qty, after_in_reserved)
    assert (final_qty, final_reserved) == (on_hand, reserved)


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_reserve_then_unreserve_returns_to_start(state: tuple[int, int], qty: int) -> None:
    """Reserve N then release N — the level returns to the starting point."""
    on_hand, reserved = state
    available = on_hand - reserved
    assume(qty <= available)
    after_qty, after_reserved = _effect("reserve", qty, on_hand, reserved)
    final_qty, final_reserved = _effect("unreserve", qty, after_qty, after_reserved)
    assert (final_qty, final_reserved) == (on_hand, reserved)


@pytest.mark.unit
@given(state=_valid_state(), delta=_ANY_DELTA)
def test_adjust_then_adjust_back_returns_to_start(state: tuple[int, int], delta: int) -> None:
    """Adjusting by ``delta`` then by ``-delta`` round-trips the row, as long
    as neither leg falls below ``reserved`` (otherwise the operation is itself
    rejected and there's nothing to undo)."""
    on_hand, reserved = state
    assume(on_hand + delta >= reserved)
    after_qty, after_reserved = _effect("adjust", delta, on_hand, reserved)
    assume(after_qty - delta >= after_reserved)
    final_qty, final_reserved = _effect("adjust", -delta, after_qty, after_reserved)
    assert (final_qty, final_reserved) == (on_hand, reserved)


# ----------------------------------------------------------------------------
# Anti-oversell core — the property the whole inventory layer exists to enforce.
# ----------------------------------------------------------------------------


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_out_never_promises_more_than_available(state: tuple[int, int], qty: int) -> None:
    """If ``out`` returns, the units we removed were already available. If
    ``qty > available`` the call MUST raise — there is no third outcome."""
    on_hand, reserved = state
    available = on_hand - reserved
    if qty <= available:
        new_qty, _ = _effect("out", qty, on_hand, reserved)
        assert new_qty >= reserved  # the units removed weren't reserved ones
    else:
        with pytest.raises(ConflictError):
            _effect("out", qty, on_hand, reserved)


@pytest.mark.unit
@given(state=_valid_state(), qty=_POSITIVE)
def test_reserve_never_promises_more_than_available(state: tuple[int, int], qty: int) -> None:
    """``reserve``'s anti-oversell guarantee mirrors ``out`` — you can't reserve
    units that don't exist or that someone else has already reserved."""
    on_hand, reserved = state
    available = on_hand - reserved
    if qty <= available:
        _new_qty, new_reserved = _effect("reserve", qty, on_hand, reserved)
        assert new_reserved <= on_hand  # reservations never exceed stock
    else:
        with pytest.raises(ConflictError):
            _effect("reserve", qty, on_hand, reserved)


def _assert_invariant(qty: int, reserved: int) -> None:
    """The post-condition every successful ``_effect`` call must satisfy —
    matches the DB CHECKs from migration 0010 (AI-2.H2)."""
    assert qty >= 0
    assert reserved >= 0
    assert reserved <= qty
