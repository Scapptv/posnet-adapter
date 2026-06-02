"""Request-ID helpers. The middleware that uses these lands with the app (AI-1.9)."""

from __future__ import annotations

from uuid import uuid4

REQUEST_ID_HEADER: str = "X-Request-ID"


def generate_request_id() -> str:
    """Generate a fresh request id (UUID4 string)."""
    return str(uuid4())
