"""AI-1.17 — core i18n wiring: get_locale, translator, /v1/i18n/messages (unit).

The messages endpoint touches no DB, so it runs in-process via TestClient with
placeholder settings (the lifespan never connects — eventbus off, no /readyz).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from services.core.app.config import Settings
from services.core.app.i18n import build_translator, get_locale
from services.core.app.main import create_app


def _request(headers: dict[str, str] | None = None, query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/i18n/messages",
            "query_string": query.encode(),
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        }
    )


@pytest.fixture
def app() -> FastAPI:
    return create_app(
        Settings(
            environment="local",
            database_url="postgresql+psycopg://u@localhost/x",
            redis_url="redis://localhost:6379/0",
            rate_limit_storage_uri="memory://",
            eventbus_enabled=False,
        )
    )


# ---- get_locale ----


@pytest.mark.unit
def test_get_locale_negotiates_accept_language() -> None:
    assert get_locale(_request({"Accept-Language": "en-US,az;q=0.8"})) == "en"


@pytest.mark.unit
def test_get_locale_query_override_wins() -> None:
    assert get_locale(_request({"Accept-Language": "en"}, query="locale=tr")) == "tr"


@pytest.mark.unit
def test_get_locale_ignores_unsupported_override() -> None:
    # Unsupported ?locale= is ignored, negotiation falls through to the default.
    assert get_locale(_request(query="locale=de")) == "az"


@pytest.mark.unit
def test_get_locale_defaults_without_header() -> None:
    assert get_locale(_request()) == "az"


# ---- translator ----


@pytest.mark.unit
def test_build_translator_defaults_to_az_with_all_locales() -> None:
    translator = build_translator()
    assert translator.default_locale == "az"
    assert set(translator.locales()) == {"az", "en", "tr", "ru"}
    assert translator.translate("ru", "auth.login") == "Войти"


# ---- endpoint ----


@pytest.mark.unit
def test_messages_endpoint_returns_negotiated_catalog(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/i18n/messages", headers={"Accept-Language": "ru"})
    assert response.status_code == 200
    body = response.json()
    assert body["locale"] == "ru"
    assert body["messages"]["app.name"] == "Posnet"
    assert body["messages"]["auth.login"] == "Войти"


@pytest.mark.unit
def test_messages_endpoint_locale_override(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/i18n/messages?locale=en", headers={"Accept-Language": "ru"})
    assert response.json()["locale"] == "en"


@pytest.mark.unit
def test_messages_endpoint_defaults_to_az(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/v1/i18n/messages")
    body = response.json()
    assert body["locale"] == "az"
    assert body["messages"]["auth.login"] == "Daxil ol"
