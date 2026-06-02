"""AI-1.9.2 / AI-1.10 — global RFC 7807 handlers (domain, validation, 500)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from services.core.app.errors import _http_error


@pytest.mark.unit
def test_domain_error_renders_problem_json(test_app: FastAPI) -> None:
    with TestClient(test_app) as client:
        response = client.get("/raise/domain")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["type"].endswith("/not-found")
    assert "widget 7" in body["detail"]
    assert "request_id" in body


@pytest.mark.unit
def test_validation_error_renders_422_problem(test_app: FastAPI) -> None:
    with TestClient(test_app) as client:
        response = client.get("/needs")  # required query param ?x missing
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["title"] == "Validation Error"
    assert isinstance(body["errors"], list)


@pytest.mark.unit
def test_unhandled_error_is_generic_500_without_leak(test_app: FastAPI) -> None:
    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/raise/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["status"] == 500
    assert body["title"] == "Internal Server Error"
    assert "request_id" in body
    assert "secret internal detail" not in str(body)  # internals never leak


@pytest.mark.unit
def test_http_exception_renders_problem_json(test_app: FastAPI) -> None:
    with TestClient(test_app) as client:
        response = client.get("/raise/http")
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 403
    assert "forbidden zone" in body["detail"]
    assert "request_id" in body


@pytest.mark.unit
async def test_problem_omits_request_id_without_middleware() -> None:
    # Handler called outside the request stack -> no request id on the scope.
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})
    response = await _http_error(request, StarletteHTTPException(status_code=404, detail="nope"))
    assert response.status_code == 404
    assert "request_id" not in json.loads(response.body)
