"""Tenant-scoped feature flag reads/writes (AI-1.17).

Both run under the caller's RLS-scoped session, so rows are implicitly limited to
the caller's tenant. ``effective_flags`` overlays the tenant's stored overrides on
the registry defaults; ``set_flag`` upserts one override (rejecting unknown keys).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.feature_flags import FlagRegistry

from ..infrastructure.db.models import FeatureFlag


async def effective_flags(session: AsyncSession, registry: FlagRegistry) -> dict[str, bool]:
    rows = (await session.execute(select(FeatureFlag.key, FeatureFlag.enabled))).tuples().all()
    return registry.resolve(dict(rows))


async def set_flag(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    key: str,
    enabled: bool,
    registry: FlagRegistry,
) -> FeatureFlag:
    """Upsert the tenant's override for ``key``; raises ``UnknownFlagError`` if the
    key is not a declared flag."""
    registry.require(key)
    existing = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        existing.enabled = enabled
        await session.flush()
        return existing

    flag = FeatureFlag(tenant_id=tenant_id, key=key, enabled=enabled)
    session.add(flag)
    await session.flush()
    await session.refresh(flag)
    return flag
