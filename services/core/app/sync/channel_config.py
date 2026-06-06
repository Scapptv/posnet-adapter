"""Typed view of ``channels.config`` JSONB (AI-2.5 deferred hardening).

The webhook + adapter wiring used to read ``channel.config`` as a raw dict with
``.get(...)`` — untyped, unvalidated, easy to mistype. :class:`ChannelConfig`
parses it once at the boundary: the common keys are typed + validated, and
adapter-specific keys survive (``extra='allow'``) so a real adapter can stash
whatever it needs. Invalid shapes raise at parse time, where the caller can turn
it into a clear error, instead of silently surfacing ``None`` deep in a push.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChannelConfig(BaseModel):
    """Validated per-channel config (the ``channels.config`` JSONB column)."""

    model_config = ConfigDict(extra="allow")

    base_url: str | None = None
    """Channel API endpoint (adapter wiring falls back to settings when absent)."""

    webhook_secret: str | None = None
    """HMAC secret for inbound webhook verification."""

    safety_stock: int = Field(default=0, ge=0)
    """Units held back from this channel (ADR-0018 §5): the hub pushes
    ``max(available - safety_stock, 0)`` so concurrent in-store sales / sync lag
    can't oversell the channel. ``0`` = push the full available quantity."""


def parse_channel_config(raw: object) -> ChannelConfig:
    """Parse a ``channels.config`` value (JSONB dict or ``None``) into a
    :class:`ChannelConfig`. A non-dict (``None``, legacy) yields defaults; a dict
    is validated (so a malformed config raises ``ValidationError`` at the
    boundary rather than misbehaving later)."""
    if isinstance(raw, dict):
        return ChannelConfig.model_validate(raw)
    return ChannelConfig()
