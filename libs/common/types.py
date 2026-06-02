"""Shared domain identifier types (UUID newtypes for tenant-scoping clarity)."""

from __future__ import annotations

from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
StoreId = NewType("StoreId", UUID)
RoleId = NewType("RoleId", UUID)
