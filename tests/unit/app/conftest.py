"""App fixtures for middleware/error tests (AI-1.9.2).

The app is built with placeholder DB/Redis URLs that are never connected (these
tests never hit /readyz), so no containers are needed — TestClient runs the
ASGI stack in-process.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException

from libs.common import NotFoundError
from services.core.app.config import Settings
from services.core.app.main import create_app


@pytest.fixture
def test_app() -> FastAPI:
    app = create_app(
        Settings(
            environment="local",
            database_url="postgresql+psycopg://u@localhost/x",
            redis_url="redis://localhost:6379/0",
        )
    )

    @app.get("/raise/domain")
    async def _domain() -> dict[str, str]:
        raise NotFoundError("widget 7 not found")

    @app.get("/raise/boom")
    async def _boom() -> dict[str, str]:
        raise ValueError("secret internal detail")

    @app.get("/raise/http")
    async def _http() -> dict[str, str]:
        raise HTTPException(status_code=403, detail="forbidden zone")

    @app.get("/needs")
    async def _needs(x: int) -> dict[str, int]:
        return {"x": x}

    return app
