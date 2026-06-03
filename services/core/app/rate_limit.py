"""Rate limiter wiring (AI-1.9.4) — slowapi over Redis (memory:// in tests).

The limiter is keyed by client IP and applies a global default limit to every
route except those explicitly exempted (health probes — infra polls them far
above any human rate). ``Limiter.enabled`` carries the on/off switch, so the
middleware can always be installed and simply pass through when disabled.

NOTE: keying is by remote address; behind a trusted proxy a future task should
key on the forwarded client IP (and, once available pre-route, per tenant).
"""

from __future__ import annotations

from collections.abc import Iterable

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.routing import BaseRoute

from .config import Settings


def build_limiter(settings: Settings) -> Limiter:
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.rate_limit_storage_uri or settings.redis_url,
        headers_enabled=True,
        enabled=settings.rate_limit_enabled,
    )


def exempt_routes(limiter: Limiter, routes: Iterable[BaseRoute]) -> None:
    """Exempt each route's endpoint from the global limit (e.g. health probes)."""
    for route in routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            # side effect: registers the route name as exempt (slowapi.exempt is untyped)
            limiter.exempt(endpoint)  # type: ignore[no-untyped-call]
