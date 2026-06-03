"""FastAPI auth + tenant dependencies (AI-1.9.3 / AI-1.11).

- ``get_principal`` turns the Bearer token into a verified :class:`Principal`
  (the :class:`TokenVerifier` is built once in the lifespan).
- ``requires_role`` / ``requires_permission`` are dependency factories wrapping
  the imperative ``libs.auth`` checks so endpoints gate declaratively.
- ``get_tenant_session`` yields a request-scoped, RLS-scoped DB session: it
  resolves the caller's tenant and switches the transaction into the
  ``posnet_app`` role with ``app.current_tenant`` set (ADR-0013/0015). A
  ``super_admin`` runs unscoped (owner role, cross-tenant).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.auth import Principal, TokenVerifier, require_permission, require_role
from libs.common import AuthError, ForbiddenError

from ..config import Settings
from ..infrastructure.db.tenant import apply_tenant_scope, resolve_tenant_id

_BEARER_PREFIX = "Bearer "


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header is None or not header.startswith(_BEARER_PREFIX):
        raise AuthError("missing or malformed Authorization header")
    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise AuthError("empty bearer token")
    return token


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:  # pragma: no cover - lifespan always builds it
        raise RuntimeError("token verifier not initialised (lifespan did not run)")
    return cast(TokenVerifier, verifier)


async def get_principal(
    request: Request,
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> Principal:
    return await verifier.verify(_bearer_token(request))


def requires_role(*roles: str) -> Callable[..., Awaitable[Principal]]:
    """Dependency that passes only if the principal has one of ``roles`` (else 403)."""

    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        require_role(principal, *roles)
        return principal

    return _dep


def requires_permission(resource: str, action: str) -> Callable[..., Awaitable[Principal]]:
    """Dependency that passes only if the principal is granted ``resource:action`` (else 403)."""

    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        require_permission(principal, resource, action)
        return principal

    return _dep


async def get_tenant_session(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> AsyncIterator[AsyncSession]:
    """Yield a DB session scoped (via RLS) to the caller's tenant."""
    settings: Settings = request.app.state.settings

    if principal.is_super_admin:
        # System role: the privileged (RLS-exempt) pool -> cross-tenant (ADR-0017).
        system_sessionmaker: async_sessionmaker[AsyncSession] = (
            request.app.state.system_sessionmaker
        )
        async with system_sessionmaker() as session, session.begin():
            request.state.tenant_id = None
            yield session
        return

    # Regular caller: the locked-down ``posnet_app`` pool. The subject->tenant
    # lookup uses the SECURITY DEFINER resolver, then the session is scoped.
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session, session.begin():
        tenant_id = await resolve_tenant_id(session, subject=principal.subject)
        if tenant_id is None:
            raise ForbiddenError("no active tenant membership for subject")
        await apply_tenant_scope(session, tenant_id, role=settings.db_app_role)
        request.state.tenant_id = tenant_id
        yield session


async def require_tenant(
    request: Request,
    _session: AsyncSession = Depends(get_tenant_session),
) -> UUID:
    """The caller's resolved tenant id (depends on the scoped session so it runs
    after resolution); 403 for a principal without a tenant (e.g. ``super_admin``),
    since tenant-scoped management has no concrete tenant to act on."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise ForbiddenError("this operation requires a tenant context")
    return cast(UUID, tenant_id)
