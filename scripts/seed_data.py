"""Seed the first tenant (idempotent). Run via ``make seed``.

The first tenant bootstraps the platform; the app's relay publishes its
``identity.tenant.onboarded`` event once running. ``admin_subject`` is a
placeholder — production seeding links the operator's real Keycloak ``sub``.

Connects as the DATABASE_URL owner role (RLS-exempt), which onboarding's
cross-tenant write requires.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.core.app.config import get_settings
from services.core.app.domain.onboarding import seed_first_tenant


async def _run() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session, session.begin():
            result = await seed_first_tenant(
                session,
                name="Posnet Pilot",
                country_code="AZ",
                plan="pro",
                admin_email="owner@posnet.local",
                admin_subject="seed-owner",
            )
        if result is None:
            print("first tenant already seeded; nothing to do")
        else:
            print(f"seeded tenant {result.tenant_id} (admin {result.admin_user_id})")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
