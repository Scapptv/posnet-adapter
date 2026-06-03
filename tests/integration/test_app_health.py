"""AI-1.9.1 — app factory + health probes against real Postgres/Redis."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.core.app.config import Settings
from services.core.app.main import create_app


def _app(database_url: str, redis_url: str) -> object:
    return create_app(
        Settings(
            database_url=database_url,
            redis_url=redis_url,
            rate_limit_storage_uri="memory://",  # isolated per-app counter
        )
    )


@pytest.mark.integration
def test_healthz_is_live(pg_sqlalchemy_url: str, redis_url: str) -> None:
    with TestClient(_app(pg_sqlalchemy_url, redis_url)) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
def test_readyz_ok_when_deps_up(pg_sqlalchemy_url: str, redis_url: str) -> None:
    with TestClient(_app(pg_sqlalchemy_url, redis_url)) as client:
        response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ready", "database": "ok", "redis": "ok"}


@pytest.mark.integration
def test_readyz_degraded_when_database_down(redis_url: str) -> None:
    unreachable = "postgresql+psycopg://x:y@127.0.0.1:1/none"
    with TestClient(_app(unreachable, redis_url)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "error"
    assert body["redis"] == "ok"


@pytest.mark.integration
def test_readyz_degraded_when_redis_down(pg_sqlalchemy_url: str) -> None:
    with TestClient(_app(pg_sqlalchemy_url, "redis://127.0.0.1:1/0")) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "ok"
    assert body["redis"] == "error"
