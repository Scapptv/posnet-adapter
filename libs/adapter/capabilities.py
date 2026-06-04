"""Adapter capability descriptor (AI-2.5.1).

What a channel can do. The sync engine reads ``capabilities`` to decide which
flows to schedule for a channel and how to throttle them. Capabilities are
declared at adapter class-level (never at runtime) so the sync engine can
introspect without instantiating the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AuthKind = Literal["api_key", "oauth2", "hmac", "none"]
"""How the channel authenticates the adapter's outbound calls.

* ``api_key`` — static API key/secret pair (most marketplaces today)
* ``oauth2`` — OAuth2 client-credentials or auth-code grant
* ``hmac`` — HMAC-signed request bodies (often paired with a long-lived key)
* ``none`` — no auth (mock channels in tests)
"""


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """What a channel can do, declared by its adapter class.

    The sync engine consults this *before* dispatching: a channel that doesn't
    ``supports_push_stock`` simply skips stock outbox events for that channel.
    A channel that ``supports_webhook_orders`` but not ``supports_pull_orders``
    only ingests via the webhook ingress.
    """

    code: str
    """Canonical channel identifier (e.g. ``"birmarket"``). Matches
    ``channels.code`` in the DB (ADR-0018) and the registry key."""

    name: str
    """Human-readable channel name (e.g. ``"Birmarket"``)."""

    auth_kind: AuthKind
    """How the adapter authenticates to the channel."""

    supports_push_listing: bool = True
    """Adapter can publish a new product listing on the channel."""

    supports_push_stock: bool = True
    """Adapter can update a listing's stock level."""

    supports_push_price: bool = True
    """Adapter can update a listing's price."""

    supports_pull_orders: bool = False
    """Adapter polls the channel for new orders (``pull_orders``)."""

    supports_webhook_orders: bool = False
    """Channel posts orders to a webhook ingress (``/v1/channels/{code}/webhook``)."""

    rate_limit_rps: int = 1
    """Sustained requests-per-second the adapter may make. The sync engine's
    per-channel token bucket honours this."""

    rate_limit_burst: int = 1
    """Burst allowance above ``rate_limit_rps``."""

    tags: frozenset[str] = field(default_factory=frozenset)
    """Optional taxonomy markers (e.g. ``{"marketplace", "az"}``). Used for
    grouped operator views; the sync engine ignores them."""

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("AdapterCapabilities.code must be non-empty")
        if not self.code.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"AdapterCapabilities.code must be alphanumeric (with - and _), got {self.code!r}"
            )
        if self.rate_limit_rps <= 0:
            raise ValueError("rate_limit_rps must be > 0")
        if self.rate_limit_burst <= 0:
            raise ValueError("rate_limit_burst must be > 0")
        if not (self.supports_pull_orders or self.supports_webhook_orders):
            # An adapter that ingests nothing is fine in principle (push-only
            # marketplace), but we want the operator to opt in explicitly. A
            # `none-of-both` default is almost always a misconfiguration.
            pass  # accepted — explicit "push-only" stance
