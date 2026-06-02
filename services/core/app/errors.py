"""Global exception handlers — RFC 7807 problem+json (AI-1.9.2 / AI-1.10).

Domain errors render via ``DomainError.to_problem`` (libs.common). Request
validation and bare HTTP errors get problem bodies too, and any unhandled
exception becomes a generic 500 that never leaks internals (the detail is
logged with a traceback instead). Every body carries the request id.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from libs.common import DomainError

from .logging_config import get_logger
from .middleware.request_id import get_request_id

_PROBLEM_JSON = "application/problem+json"
_logger = get_logger("posnet.errors")


def _problem(status: int, body: dict[str, Any], request: Request) -> JSONResponse:
    request_id = get_request_id(request)
    if request_id is not None:
        body.setdefault("request_id", request_id)
    return JSONResponse(status_code=status, content=body, media_type=_PROBLEM_JSON)


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return _problem(exc.status, exc.to_problem(), request)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "https://posnet.io/errors/validation",
        "title": "Validation Error",
        "status": 422,
        "detail": "Request validation failed",
        "errors": jsonable_encoder(exc.errors()),
    }
    return _problem(422, body, request)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": "HTTP Error",
        "status": exc.status_code,
        "detail": str(exc.detail),
    }
    return _problem(exc.status_code, body, request)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    _logger.error("unhandled_exception", exc_info=exc)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected error occurred.",
    }
    return _problem(500, body, request)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)
