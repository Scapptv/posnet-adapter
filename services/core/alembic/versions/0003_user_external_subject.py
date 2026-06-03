"""user external_subject (Keycloak sub -> tenant resolution, ADR-0015)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Globally unique (across tenants): one Keycloak subject = one DB user; the
    # per-request tenant lookup keys on it (ADR-0015). Nullable: legacy/seed and
    # not-yet-onboarded users have no IdP link.
    op.add_column("users", sa.Column("external_subject", sa.String(length=255), nullable=True))
    op.create_index(
        op.f("ix_users_external_subject"),
        "users",
        ["external_subject"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_external_subject"), table_name="users")
    op.drop_column("users", "external_subject")
