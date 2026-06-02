"""Money as integer minor units + ISO 4217 currency.

No floats are ever used — amounts are integer minor units (qəpik / kuruş), so
rounding never loses a sub-unit. See LOCKED decision #3 (AI-ROADMAP §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# ISO 4217 minor-unit exponents; default 2. Beachhead currencies AZN, TRY are both 2.
_EXPONENTS: Final[dict[str, int]] = {
    "AZN": 2,
    "TRY": 2,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
}


def minor_unit_exponent(currency: str) -> int:
    """Number of decimal places for ``currency`` (default 2 if unknown)."""
    return _EXPONENTS.get(currency, 2)


def validate_currency_code(code: str) -> str:
    """Return ``code`` unchanged if it is a 3-letter upper-case ISO 4217 code.

    Shared by :class:`Money` and the canonical model's ``CurrencyCode`` so both
    enforce the same rule. Does not check the code against the ISO registry.
    """
    if len(code) != 3 or not code.isalpha() or not code.isupper():
        raise ValueError(f"invalid ISO 4217 currency code: {code!r}")
    return code


@dataclass(frozen=True, slots=True)
class Money:
    """An amount expressed in integer minor units of an ISO 4217 currency."""

    minor: int
    currency: str

    def __post_init__(self) -> None:
        validate_currency_code(self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.minor - other.minor, self.currency)

    def __mul__(self, quantity: int) -> Money:
        return Money(self.minor * quantity, self.currency)

    @property
    def major(self) -> Decimal:
        """Decimal value in major units (e.g. 12345 minor AZN -> Decimal('123.45'))."""
        return Decimal(self.minor).scaleb(-minor_unit_exponent(self.currency))

    def __str__(self) -> str:
        return f"{self.major} {self.currency}"
