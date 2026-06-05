"""AI-2.2 follow-up — ``transfer_stock`` input guards (unit, no DB).

The ``qty > 0`` guard rejects before any DB access, so it's covered here without
a container — the API's ``Field(gt=0)`` is the edge layer, but a direct domain
caller must still be rejected. The DB-backed transfer paths (atomic move,
anti-oversell, unknown destination) live in ``test_inventory_api``.
"""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common import ValidationError
from services.core.app.domain.inventory import transfer_stock


@pytest.mark.unit
async def test_transfer_rejects_nonpositive_qty() -> None:
    """qty <= 0 raises before the session is ever touched (so ``None`` is safe)."""
    with pytest.raises(ValidationError):
        await transfer_stock(
            cast(AsyncSession, None),
            tenant_id=uuid4(),
            variant_id=uuid4(),
            from_warehouse_id=uuid4(),
            to_warehouse_id=uuid4(),
            qty=0,
        )
