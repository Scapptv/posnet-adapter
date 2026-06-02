"""Unit tests for the domain error hierarchy + RFC 7807 mapping."""

from __future__ import annotations

import pytest

from libs.common.errors import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


def test_status_codes() -> None:
    assert NotFoundError("x").status == 404
    assert ConflictError("x").status == 409
    assert ValidationError("x").status == 422
    assert AuthError("x").status == 401
    assert ForbiddenError("x").status == 403
    assert RateLimitError("x").status == 429


def test_to_problem_full() -> None:
    err = NotFoundError("User 123 not found", instance="/v1/users/123")
    problem = err.to_problem(trace_id="trace-abc", request_id="req-1")
    assert problem == {
        "type": "https://posnet.io/errors/not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "User 123 not found",
        "instance": "/v1/users/123",
        "trace_id": "trace-abc",
        "request_id": "req-1",
    }


def test_to_problem_minimal() -> None:
    problem = ConflictError("duplicate slug").to_problem()
    assert set(problem) == {"type", "title", "status", "detail"}
    assert problem["status"] == 409


def test_extra_fields_merge() -> None:
    err = ValidationError("invalid body", extra={"errors": [{"field": "email"}]})
    assert err.to_problem()["errors"] == [{"field": "email"}]


def test_is_raisable_exception() -> None:
    with pytest.raises(DomainError):
        raise NotFoundError("nope")
