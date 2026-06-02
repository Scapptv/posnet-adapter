"""Request-ID middleware (AI-1.9.2).

Pure ASGI (not BaseHTTPMiddleware) so the contextvar it sets is visible in the
same task to the endpoint and the logger. The id is also stashed on the scope
under a private key, which survives the contextvar reset — so the 500 handler
(run by the outermost ServerErrorMiddleware, after this middleware's ``finally``)
can still read it.
"""

from __future__ import annotations

import contextvars

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from libs.common import REQUEST_ID_HEADER, generate_request_id

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_SCOPE_KEY = "posnet.request_id"
_HEADER_LOWER = REQUEST_ID_HEADER.lower().encode()


def get_request_id(request: Request) -> str | None:
    value = request.scope.get(_SCOPE_KEY)
    return value if isinstance(value, str) else None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._incoming(scope) or generate_request_id()
        scope[_SCOPE_KEY] = request_id
        token = request_id_ctx.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(raw=message["headers"])[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)

    @staticmethod
    def _incoming(scope: Scope) -> str | None:
        headers: list[tuple[bytes, bytes]] = scope["headers"]
        for key, value in headers:
            if key == _HEADER_LOWER:
                return value.decode()
        return None
