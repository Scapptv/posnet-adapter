"""outbox_events.seq — monotonic relay ordering (H4, ADR-0020)

The relay drained ``ORDER BY created_at``, but ``created_at`` is transaction
time: every event enqueued in one business transaction shares the same
timestamp, so the relay (and the downstream consumer) could emit them in an
arbitrary order. For the hub that means two ``inventory.movement.applied``
events from one multi-line reservation could reach a channel out of order,
leaving the channel on a stale stock snapshot.

A monotonic ``seq`` (BIGSERIAL) gives a total insertion order so the relay can
``ORDER BY seq`` and preserve enqueue order within (and across) transactions.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # BIGSERIAL backfills existing rows in physical (≈insertion) order and sets a
    # NOT NULL nextval default for new rows — every future event gets a strictly
    # increasing seq.
    op.execute("ALTER TABLE outbox_events ADD COLUMN seq BIGSERIAL NOT NULL")
    # Partial index matching the relay's hot path: WHERE NOT published ORDER BY seq.
    op.execute(
        "CREATE INDEX ix_outbox_events_unpublished_seq "
        "ON outbox_events (seq) WHERE NOT published"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outbox_events_unpublished_seq")
    # Dropping the column also drops the owned BIGSERIAL sequence.
    op.execute("ALTER TABLE outbox_events DROP COLUMN IF EXISTS seq")
