"""Per-request tenant resolution + RLS scoping (AI-1.11, ADR-0013/0015).

``resolve_tenant_id`` maps a verified Keycloak subject to its tenant via the
``users.external_subject`` link. It must run *before* the role switch — as the
connection's owner login role, which is RLS-exempt — so it can see users across
tenants to find the match.

``apply_tenant_scope`` then switches the transaction into the non-owner
``posnet_app`` role and sets ``app.current_tenant`` (both ``LOCAL``, so they
reset when the request transaction ends). From that point every statement is
RLS-enforced to the resolved tenant (ADR-0013: "per-request ``posnet_app`` rolu").
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Active user only: a disabled user must not acquire tenant context.
_RESOLVE_TENANT_SQL = text(
    "SELECT tenant_id FROM users WHERE external_subject = :subject AND status = 'active'"
)
_SET_TENANT_SQL = text("SELECT set_config('app.current_tenant', :tenant_id, true)")

# Postgres identifier — guards the role name we must interpolate (SET LOCAL ROLE
# cannot take a bind parameter). The value comes from trusted settings, never
# from a request, but we validate it anyway (defence in depth).
_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def resolve_tenant_id(session: AsyncSession, *, subject: str) -> uuid.UUID | None:
    """Return the tenant of the active user linked to ``subject``, or ``None``."""
    result = await session.execute(_RESOLVE_TENANT_SQL, {"subject": subject})
    row = result.first()
    if row is None:
        return None
    return uuid.UUID(str(row[0]))


async def apply_tenant_scope(
    session: AsyncSession, tenant_id: uuid.UUID, *, role: str = "posnet_app"
) -> None:
    """Switch the current transaction into ``role`` scoped to ``tenant_id`` (RLS)."""
    if not _ROLE_RE.match(role):
        raise ValueError(f"invalid app DB role: {role!r}")
    # SET LOCAL ROLE cannot bind a parameter; ``role`` is a validated identifier
    # from trusted settings (never request input).
    await session.execute(text(f'SET LOCAL ROLE "{role}"'))
    await session.execute(_SET_TENANT_SQL, {"tenant_id": str(tenant_id)})
