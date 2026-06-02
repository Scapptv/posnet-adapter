"""Access logging middleware (AI-1.9.2).

Pure ASGI: one structured ``request`` event per HTTP request with method, path,
status and duration. Logs in ``finally`` so failed requests are recorded too;
request_id is injected by the logging processor.
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..logging_config import get_logger

_logger = get_logger("posnet.request")


class LoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status = 0

        async def send_capturing_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_capturing_status)
        finally:
            _logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status,
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            )
