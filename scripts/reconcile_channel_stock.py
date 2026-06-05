"""Reconcile channel stock/price vs POS for every tenant. Run via ``make reconcile``.

Intended as a cron / Kubernetes CronJob entrypoint (roadmap §17.4). For each
tenant it scopes a session to that tenant's RLS context and runs
``reconcile_tenant`` with the production adapter factory (H6, ADR-0020):
``register_builtin_adapters`` installs the shipped adapters (mock marketplace for
dev/demo; real adapters self-register on import) and ``build_adapter_factory``
resolves each channel's ``code`` to a configured adapter. Channels whose code has
no registered adapter are skipped.

Connects as the DATABASE_URL owner (RLS-exempt); the per-tenant scope is applied
explicitly via ``apply_tenant_scope`` before reconciling.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.core.app.config import get_settings
from services.core.app.infrastructure.db.models import Tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.reconcile import reconcile_tenant
from services.core.app.sync.wiring import build_adapter_factory, register_builtin_adapters

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("reconcile")


async def _run() -> None:
    settings = get_settings()
    register_builtin_adapters()
    adapter_factory = build_adapter_factory(settings)
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()

        for tenant_id in tenant_ids:
            async with factory() as session, session.begin():
                await apply_tenant_scope(session, tenant_id)
                report = await reconcile_tenant(session, adapter_factory=adapter_factory)
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
