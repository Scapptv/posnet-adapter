"""Sync every tenant's Posnet catalog into the hub. Run via ``make pos-sync``.

Cron / Kubernetes CronJob entrypoint for the POS *pull* side (roadmap §17.7
"dövri sync") — the inbound mirror of ``reconcile_channel_stock`` on the push
side. For each tenant it resolves the tenant's POS connector via
``build_pos_source_factory`` (from ``POSNET_BASE_URL``); tenants with no POS
configured are skipped, so the job is a safe no-op until a Posnet is wired.

Connects as the ``DATABASE_URL`` owner (RLS-exempt); the per-tenant scope is
applied explicitly via ``apply_tenant_scope`` before syncing. Each tenant's
connector is closed after use (it owns an httpx client).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.core.app.config import get_settings
from services.core.app.infrastructure.db.models import Tenant
from services.core.app.infrastructure.db.tenant import apply_tenant_scope
from services.core.app.sync.pos_ingest import sync_tenant_catalog_from_pos
from services.core.app.sync.wiring import build_pos_source_factory

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("pos-sync")


async def _run() -> None:
    settings = get_settings()
    pos_factory = build_pos_source_factory(settings)
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()

        for tenant_id in tenant_ids:
            source = pos_factory(tenant_id)
            if source is None:
                continue  # no POS connected for this tenant — skip
            try:
                async with factory() as session, session.begin():
                    await apply_tenant_scope(session, tenant_id)
                    report = await sync_tenant_catalog_from_pos(
                        session, tenant_id=tenant_id, source=source
                    )
                if report is None:
                    _log.info("tenant %s: no online warehouse, skipped", tenant_id)
                else:
                    _log.info(
                        "synced tenant %s: pulled=%d created=%d updated=%d restocked=%d",
                        tenant_id,
                        report.pulled,
                        report.created,
                        report.updated,
                        report.restocked,
                    )
            finally:
                aclose = getattr(source, "aclose", None)
                if aclose is not None:
                    await aclose()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
