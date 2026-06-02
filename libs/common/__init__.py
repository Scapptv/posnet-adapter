"""Shared infrastructure library used across all Posnet services."""

from __future__ import annotations

from .errors import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from .money import Money, minor_unit_exponent, validate_currency_code
from .request_id import REQUEST_ID_HEADER, generate_request_id
from .types import RoleId, StoreId, TenantId, UserId

__all__ = [
    "REQUEST_ID_HEADER",
    "AuthError",
    "ConflictError",
    "DomainError",
    "ForbiddenError",
    "Money",
    "NotFoundError",
    "RateLimitError",
    "RoleId",
    "StoreId",
    "TenantId",
    "UserId",
    "ValidationError",
    "generate_request_id",
    "minor_unit_exponent",
    "validate_currency_code",
]
