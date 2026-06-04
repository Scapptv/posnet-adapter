"""Reconcile channel stock/price vs POS for every tenant. Run via ``make reconcile``.

Intended as a cron / Kubernetes CronJob entrypoint (roadmap §17.4). For each
tenant it scopes a session to that tenant's RLS context and runs
``reconcile_tenant`` with an adapter resolved from the registry. Channels whose
``code`` has no registered adapter are skipped — a real adapter self-registers
on import; until then the channel is inert (the registry is empty pre-G-V, so
this run is a structural no-op today).

Connects as the DATABASE_URL owner (RLS-exempt); the per-tenant scope is applied
explicitly via ``apply_tenant_scope`` before reconciling.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from libs.adapter import ChannelAdapter, get_adapter
from services.core.app.config import get_settings
from services.core.app.infrastructure.db.models import Channel, Tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.reconcile import reconcile_tenant

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("reconcile")


async def _adapter_factory(channel: Channel) -> ChannelAdapter:
    """Resolve a channel to its adapter via the registry.

    ``get_adapter`` raises ``AdapterNotFoundError`` for an unregistered code,
    which ``reconcile_tenant`` treats as "skip this channel". Real adapters
    self-register on import and define their own config-driven construction
    (base_url + Vault secrets from ``channel.config``); that wiring lands with
    the first real adapter (post-G-V).
    """
    adapter_cls = get_adapter(channel.code)
    return adapter_cls()  # real construction wired with the first concrete adapter


async def _run() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()

        for tenant_id in tenant_ids:
            async with factory() as session, session.begin():
                await apply_tenant_scope(session, tenant_id)
                report = await reconcile_tenant(session, adapter_factory=_adapter_factory)
            _log.info(
                "reconciled tenant %s: checked=%d drifted=%d repaired=%d",
                tenant_id,
                report.checked,
                report.drifted,
                report.repaired,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
