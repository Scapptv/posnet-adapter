"""Authenticated caller derived from a verified token (AI-1.8)."""

from __future__ import annotations

from dataclasses import dataclass

SUPER_ADMIN = "super_admin"


@dataclass(frozen=True)
class Principal:
    """The verified identity. ``roles`` are realm roles from the token.

    Carries only AuthN claims; tenant resolution (token attribute vs DB lookup)
    is decided in AI-1.11 (ADR-0014), so there is deliberately no ``tenant_id``.
    """

    subject: str
    username: str | None
    email: str | None
    roles: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_super_admin(self) -> bool:
        return SUPER_ADMIN in self.roles
