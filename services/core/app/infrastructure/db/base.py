"""SQLAlchemy 2.0 declarative base and shared column mixins.

Conventions (AI-ROADMAP §15): UUID v4 primary keys (``gen_random_uuid()``),
``TIMESTAMPTZ`` everywhere (never naive), tenant_id on every tenant-scoped table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Posnet core models."""


class UUIDPrimaryKeyMixin:
    """UUID primary key with a DB-side ``gen_random_uuid()`` default."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` as TIMESTAMPTZ with DB-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
