"""Domain error hierarchy with RFC 7807 (problem+json) mapping.

Each domain error carries an HTTP status, a stable type URI and a human title.
``to_problem()`` renders the RFC 7807 body used by the global error handler (AI-1.10).
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base domain error. Subclasses set ``status`` / ``title`` / ``error_type``."""

    status: int = 500
    title: str = "Internal Server Error"
    error_type: str = "about:blank"

    def __init__(
        self,
        detail: str,
        *,
        instance: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.instance = instance
        self.extra: dict[str, Any] = extra or {}

    def to_problem(
        self,
        *,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Render the RFC 7807 problem+json body."""
        problem: dict[str, Any] = {
            "type": self.error_type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        if self.instance is not None:
            problem["instance"] = self.instance
        if trace_id is not None:
            problem["trace_id"] = trace_id
        if request_id is not None:
            problem["request_id"] = request_id
        problem.update(self.extra)
        return problem


class NotFoundError(DomainError):
    status = 404
    title = "Not Found"
    error_type = "https://posnet.io/errors/not-found"


class ConflictError(DomainError):
    status = 409
    title = "Conflict"
    error_type = "https://posnet.io/errors/conflict"


class ValidationError(DomainError):
    status = 422
    title = "Validation Error"
    error_type = "https://posnet.io/errors/validation"


class AuthError(DomainError):
    status = 401
    title = "Unauthorized"
    error_type = "https://posnet.io/errors/unauthorized"


class ForbiddenError(DomainError):
    status = 403
    title = "Forbidden"
    error_type = "https://posnet.io/errors/forbidden"


class RateLimitError(DomainError):
    status = 429
    title = "Too Many Requests"
    error_type = "https://posnet.io/errors/rate-limit"
