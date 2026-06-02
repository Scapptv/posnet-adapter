"""Canonical model foundation (AI-1.4).

Channel-agnostic, immutable Pydantic v2 schemas — the hub's single truth that
every channel adapter maps to and from. Strict by contract: unknown fields are
rejected so a sloppy adapter mapping fails loudly rather than silently dropping
data. Versioned as ``v1`` (see ``CanonicalBase.schema_version``).
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict

from libs.common import validate_currency_code

CurrencyCode = Annotated[str, AfterValidator(validate_currency_code)]
"""ISO 4217 alpha code, validated with the same rule as :class:`libs.common.Money`."""


class CanonicalBase(BaseModel):
    """Immutable, strict base for every canonical schema."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: ClassVar[str] = "v1"
