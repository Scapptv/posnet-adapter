"""Tenant onboarding (AI-1.15).

Creates a tenant and its first admin user, and emits ``identity.tenant.onboarded``
into the transactional outbox — all inside the caller's transaction, so the rows
and the event commit together (the relay publishes the event afterwards).

This is a cross-tenant write (a *new* tenant has no existing context), so the
caller must provide an RLS-exempt session — the owner session that
``get_tenant_session`` yields for a ``super_admin`` (ADR-0013/0015), or the seed
script's owner connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.eventbus import Event, enqueue

from ..infrastructure.db.models import Tenant, User

TENANT_ONBOARDED = "identity.tenant.onboarded"


@dataclass(frozen=True)
class TenantOnboarded:
    tenant_id: UUID
    admin_user_id: UUID
    name: str
    status: str


async def onboard_tenant(
    session: AsyncSession,
    *,
    name: str,
    country_code: str,
    plan: str,
    admin_email: str,
    admin_subject: str,
) -> TenantOnboarded:
    """Create the tenant + admin user and enqueue the onboarded event."""
    tenant = Tenant(name=name, country_code=country_code, plan=plan)
    session.add(tenant)
    await session.flush()  # assigns tenant.id (server-side gen_random_uuid)

    admin = User(tenant_id=tenant.id, email=admin_email, external_subject=admin_subject)
    session.add(admin)
    await session.flush()  # assigns admin.id; raises IntegrityError on duplicate subject/email

    await session.refresh(tenant)  # pull server defaults (status, timestamps)
    await enqueue(
        session,
        Event(
            event_type=TENANT_ONBOARDED,
            tenant_id=tenant.id,
            payload={
                "tenant_id": str(tenant.id),
                "admin_user_id": str(admin.id),
                "name": name,
                "country_code": country_code,
            },
        ),
    )
    return TenantOnboarded(
        tenant_id=tenant.id, admin_user_id=admin.id, name=tenant.name, status=tenant.status
    )


async def seed_first_tenant(
    session: AsyncSession,
    *,
    name: str,
    country_code: str,
    plan: str,
    admin_email: str,
    admin_subject: str,
) -> TenantOnboarded | None:
    """Idempotent onboarding for bootstrap: skip (return ``None``) if the admin
    subject already exists, else onboard."""
    existing = await session.execute(select(User.id).where(User.external_subject == admin_subject))
    if existing.first() is not None:
        return None
    return await onboard_tenant(
        session,
        name=name,
        country_code=country_code,
        plan=plan,
        admin_email=admin_email,
        admin_subject=admin_subject,
    )
