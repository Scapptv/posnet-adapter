"""Role / permission checks (AI-1.8).

``require_role`` is the primary gate — roles ride in the token, so it works with
nothing but a verified :class:`Principal`. ``require_permission`` resolves a
``(resource, action)`` against a static foundation map; AI-1.16 will make
permissions per-tenant and DB-driven (table ``permissions``), at which point
this map becomes the fallback/default. ``super_admin`` bypasses every check.
"""

from __future__ import annotations

from libs.common import ForbiddenError

from .principal import Principal

_WILDCARD = "*"

# Foundation default RBAC: role -> granted (resource, action) pairs.
ROLE_PERMISSIONS: dict[str, frozenset[tuple[str, str]]] = {
    "super_admin": frozenset({(_WILDCARD, _WILDCARD)}),
    "tenant_admin": frozenset({(_WILDCARD, _WILDCARD)}),  # full control, RLS-scoped to the tenant
    "store_manager": frozenset(
        {
            ("catalog", "read"),
            ("catalog", "write"),
            ("inventory", "read"),
            ("inventory", "write"),
            ("pricing", "read"),
            ("pricing", "write"),
            ("order", "read"),
            ("order", "write"),
            ("shift", "read"),
            ("shift", "write"),
        }
    ),
    "cashier": frozenset(
        {
            ("catalog", "read"),
            ("inventory", "read"),
            ("sale", "write"),
            ("shift", "read"),
            ("shift", "write"),
        }
    ),
    "clerk": frozenset(
        {
            ("catalog", "read"),
            ("catalog", "write"),
            ("inventory", "read"),
            ("inventory", "write"),
        }
    ),
}


def require_role(principal: Principal, *roles: str) -> None:
    """Raise ``ForbiddenError`` unless the caller has one of ``roles``."""
    if principal.is_super_admin:
        return
    if not any(principal.has_role(role) for role in roles):
        raise ForbiddenError(f"requires one of roles: {', '.join(roles)}")


def has_permission(principal: Principal, resource: str, action: str) -> bool:
    for role in principal.roles:
        for granted_resource, granted_action in ROLE_PERMISSIONS.get(role, frozenset()):
            if granted_resource in (resource, _WILDCARD) and granted_action in (action, _WILDCARD):
                return True
    return False


def require_permission(principal: Principal, resource: str, action: str) -> None:
    """Raise ``ForbiddenError`` unless the caller's roles grant ``resource:action``."""
    if not has_permission(principal, resource, action):
        raise ForbiddenError(f"requires permission: {resource}:{action}")
