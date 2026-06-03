"""Unit tests for Money (integer minor units, no float)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from libs.common.money import Money, minor_unit_exponent, validate_currency_code

_MINOR = st.integers(min_value=-(10**12), max_value=10**12)


def test_add_same_currency() -> None:
    assert Money(100, "AZN") + Money(250, "AZN") == Money(350, "AZN")


def test_sub_and_mul() -> None:
    assert Money(500, "AZN") - Money(200, "AZN") == Money(300, "AZN")
    assert Money(100, "AZN") * 3 == Money(300, "AZN")


def test_currency_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = Money(100, "AZN") + Money(100, "TRY")


@pytest.mark.parametrize("bad", ["azn", "AZ", "AZNN", "A1N", "123"])
def test_invalid_currency_raises(bad: str) -> None:
    with pytest.raises(ValueError, match="currency"):
        Money(100, bad)


def test_validate_currency_code_returns_input() -> None:
    assert validate_currency_code("AZN") == "AZN"


@pytest.mark.parametrize("bad", ["azn", "AZ", "AZNN", "A1N"])
def test_validate_currency_code_rejects(bad: str) -> None:
    with pytest.raises(ValueError, match="currency"):
        validate_currency_code(bad)


def test_major_is_exact_decimal() -> None:
    assert Money(12345, "AZN").major == Decimal("123.45")
    assert Money(12345, "JPY").major == Decimal("12345")
    assert minor_unit_exponent("AZN") == 2
    assert minor_unit_exponent("JPY") == 0
    assert minor_unit_exponent("XYZ") == 2  # unknown -> default 2


def test_str() -> None:
    assert str(Money(12345, "AZN")) == "123.45 AZN"


@given(a=_MINOR, b=_MINOR, c=_MINOR)
def test_add_associative(a: int, b: int, c: int) -> None:
    x, y, z = Money(a, "AZN"), Money(b, "AZN"), Money(c, "AZN")
    assert (x + y) + z == x + (y + z)


@given(a=_MINOR, b=_MINOR)
def test_add_commutative(a: int, b: int) -> None:
    assert Money(a, "AZN") + Money(b, "AZN") == Money(b, "AZN") + Money(a, "AZN")


# ---- AI-2.H3 — property tests for sub/mul + algebraic round-trips (audit A5) ----


_SMALL = st.integers(min_value=-1000, max_value=1000)
# 3 ASCII upper-case letters — every value Hypothesis generates is a valid
# ISO-4217 *shape* (Money does not check the ISO registry, only the format).
_CURRENCY = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=3, max_size=3
)


@given(a=_MINOR, b=_MINOR)
def test_sub_preserves_minor_arithmetic(a: int, b: int) -> None:
    assert (Money(a, "AZN") - Money(b, "AZN")).minor == a - b


@given(a=_MINOR)
def test_self_subtraction_is_zero(a: int) -> None:
    assert Money(a, "AZN") - Money(a, "AZN") == Money(0, "AZN")


@given(a=_MINOR, b=_MINOR)
def test_add_then_subtract_is_identity(a: int, b: int) -> None:
    """``(a + b) - b == a`` — subtraction undoes addition."""
    x, y = Money(a, "AZN"), Money(b, "AZN")
    assert (x + y) - y == x


@given(a=_MINOR, n=_SMALL)
def test_mul_distributes_over_minor(a: int, n: int) -> None:
    assert (Money(a, "AZN") * n).minor == a * n


@given(a=_MINOR)
def test_mul_by_one_is_identity(a: int) -> None:
    assert Money(a, "AZN") * 1 == Money(a, "AZN")


@given(a=_MINOR)
def test_mul_by_zero_is_zero(a: int) -> None:
    assert Money(a, "AZN") * 0 == Money(0, "AZN")


@given(a=_MINOR, b=_MINOR, currency=_CURRENCY)
def test_arithmetic_preserves_currency(a: int, b: int, currency: str) -> None:
    """Every arithmetic result carries the operands' currency; mixing currencies
    raises (covered in unit examples), so the property only needs same-currency
    operands here."""
    x, y = Money(a, currency), Money(b, currency)
    assert (x + y).currency == currency
    assert (x - y).currency == currency
    assert (x * 3).currency == currency


@given(a=_MINOR, b=_MINOR, c1=_CURRENCY, c2=_CURRENCY)
def test_mixed_currency_always_raises(a: int, b: int, c1: str, c2: str) -> None:
    """Money is currency-strict — no implicit conversion at any minor value."""
    assume(c1 != c2)
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = Money(a, c1) + Money(b, c2)
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = Money(a, c1) - Money(b, c2)


@given(a=_MINOR)
def test_major_round_trips_through_minor(a: int) -> None:
    """``major`` is a faithful presentation: scaling back by the currency's
    exponent recovers the integer minor value exactly. No rounding error."""
    money = Money(a, "AZN")
    assert int(money.major.scaleb(2)) == a
