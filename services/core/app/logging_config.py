"""structlog configuration (AI-1.9.2) — the logger deferred from AI-1.2.

JSON in deployed environments, human-readable console locally. Every event is
stamped with the current request's id (pulled from the request-id contextvar),
so logs correlate with the ``X-Request-ID`` response header and RFC 7807 bodies.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from libs.observability import add_trace_context

from .middleware.request_id import request_id_ctx


def add_request_id(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    request_id = request_id_ctx.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(*, json_logs: bool = True, level: int = logging.INFO) -> None:
    processors: list[structlog.types.Processor] = [
        structlog.processors.add_log_level,
        add_request_id,
        add_trace_context,  # trace_id/span_id when a span is active (AI-1.13)
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if json_logs:
        # JSONRenderer needs exc_info flattened to a string; ConsoleRenderer does
        # its own exception formatting (and warns if format_exc_info is present).
        processors += [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
