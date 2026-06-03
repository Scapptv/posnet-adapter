"""Security headers middleware (AI-1.9.4).

Pure ASGI (like RequestId): stamps the standard hardening headers on every HTTP
response. Values are precomputed once from settings; HSTS/CSP are omitted when
configured empty. Existing headers are not clobbered (a route may set its own).
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Always-on constants (no value to make configurable).
_CONSTANT_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, csp: str = "", hsts: str = "") -> None:
        self.app = app
        headers: list[tuple[str, str]] = list(_CONSTANT_HEADERS)
        if hsts:
            headers.append(("Strict-Transport-Security", hsts))
        if csp:
            headers.append(("Content-Security-Policy", csp))
        self._headers = tuple(headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                for name, value in self._headers:
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
