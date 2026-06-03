"""AI-1.9.4 / AI-1.12 — CORS, security headers, rate limiting (unit, no IO).

Apps use ``memory://`` rate-limit storage so each ``create_app`` gets an isolated
counter (no shared Redis, no cross-test bleed).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from services.core.app.config import Settings
from services.core.app.main import create_app
from services.core.app.rate_limit import build_limiter, exempt_routes


def _app(**overrides: Any) -> FastAPI:
    base: dict[str, Any] = {
        "environment": "local",
        "database_url": "postgresql+psycopg://u@localhost/x",
        "redis_url": "redis://localhost:6379/0",
        "rate_limit_storage_uri": "memory://",
    }
    base.update(overrides)
    app = create_app(Settings(**base))

    @app.get("/ping")
    async def _ping() -> dict[str, bool]:
        return {"pong": True}

    @app.get("/own-header")
    async def _own_header(response: Response) -> dict[str, bool]:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"  # route sets its own
        return {"ok": True}

    return app


# ---- security headers ----


@pytest.mark.unit
def test_security_headers_present() -> None:
    with TestClient(_app()) as client:
        response = client.get("/ping")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert "default-src" in response.headers["Content-Security-Policy"]


@pytest.mark.unit
def test_security_headers_configurable() -> None:
    app = _app(security_csp="default-src 'self'", security_hsts="")
    with TestClient(app) as client:
        response = client.get("/ping")
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert "Strict-Transport-Security" not in response.headers  # empty -> omitted


@pytest.mark.unit
def test_security_headers_can_be_disabled() -> None:
    app = _app(security_headers_enabled=False)
    with TestClient(app) as client:
        response = client.get("/ping")
    assert "X-Frame-Options" not in response.headers


@pytest.mark.unit
def test_security_headers_omitted_when_empty() -> None:
    app = _app(security_csp="", security_hsts="")
    with TestClient(app) as client:
        response = client.get("/ping")
    assert "Content-Security-Policy" not in response.headers
    assert "Strict-Transport-Security" not in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"  # constants still applied


@pytest.mark.unit
def test_security_headers_do_not_clobber_route_value() -> None:
    with TestClient(_app()) as client:
        response = client.get("/own-header")
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"  # route's value preserved


# ---- CORS ----


@pytest.mark.unit
def test_cors_allows_configured_origin() -> None:
    app = _app(cors_allow_origins="https://admin.posnet.local")
    with TestClient(app) as client:
        response = client.get("/ping", headers={"Origin": "https://admin.posnet.local"})
    assert response.headers["access-control-allow-origin"] == "https://admin.posnet.local"


@pytest.mark.unit
def test_cors_preflight_allowed_origin() -> None:
    app = _app(cors_allow_origins="https://admin.posnet.local")
    with TestClient(app) as client:
        response = client.options(
            "/ping",
            headers={
                "Origin": "https://admin.posnet.local",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://admin.posnet.local"


@pytest.mark.unit
def test_cors_blocks_unconfigured_origin() -> None:
    app = _app(cors_allow_origins="https://admin.posnet.local")
    with TestClient(app) as client:
        response = client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


# ---- rate limiting ----


@pytest.mark.unit
def test_rate_limit_returns_429_problem_json() -> None:
    app = _app(rate_limit_default="3/minute")
    with TestClient(app) as client:
        allowed = [client.get("/ping").status_code for _ in range(3)]
        blocked = client.get("/ping")
    assert allowed == [200, 200, 200]
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")
    body = blocked.json()
    assert body["status"] == 429
    assert body["title"] == "Too Many Requests"
    assert "request_id" in body
    assert blocked.headers.get("X-Request-ID")  # outer RequestId middleware still ran


@pytest.mark.unit
def test_health_probe_is_exempt_from_rate_limit() -> None:
    app = _app(rate_limit_default="2/minute")
    with TestClient(app) as client:
        statuses = [client.get("/healthz").status_code for _ in range(5)]
    assert statuses == [200, 200, 200, 200, 200]  # never throttled


@pytest.mark.unit
def test_rate_limit_can_be_disabled() -> None:
    app = _app(rate_limit_default="1/minute", rate_limit_enabled=False)
    with TestClient(app) as client:
        statuses = [client.get("/ping").status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 200]


@pytest.mark.unit
def test_exempt_routes_ignores_endpointless() -> None:
    limiter = build_limiter(Settings(rate_limit_storage_uri="memory://"))

    class _Routeless:  # a Mount-like route without an ``endpoint``
        pass

    assert exempt_routes(limiter, [_Routeless()]) is None  # type: ignore[list-item]  # skipped, no error
