"""AI-2.5.4 — webhook ingress end-to-end.

Drives ``POST /v1/channels/{tenant_id}/{code}/webhook`` against the real app
with a stub adapter factory pointing at :class:`MockMarketplaceAdapter`.
Covers the contract:

* valid HMAC + valid body → ``200``, channel_orders row inserted.
* redelivered webhook (same channel_order_id) → ``200`` with
  ``status="duplicate"``, no second row.
* bad signature → ``401``, no row.
* unknown channel → ``404``.
* paused channel → ``404``.
* malformed body → ``400`` (adapter raises ``AdapterPermanentError``).
* missing webhook secret → ``503``.
* factory not wired → ``503``.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator
from typing import cast

import orjson
import psycopg
import pytest
from fastapi.testclient import TestClient

from libs.adapter import ChannelAdapter
from services.core.app.adapters.mock_marketplace import (
    MockMarketplaceAdapter,
    MockMarketplaceConfig,
)
from services.core.app.config import Settings
from services.core.app.infrastructure.db.models import Channel
from services.core.app.main import create_app

SECRET = "test-webhook-secret-2026"  # pragma: allowlist secret


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _adapter() -> ChannelAdapter:
    return cast(
        ChannelAdapter,
        MockMarketplaceAdapter(MockMarketplaceConfig(base_url="http://mock")),
    )


def _factory(_channel: Channel) -> ChannelAdapter:
    return _adapter()


@pytest.fixture
def app_with_factory(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str
) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_sqlalchemy_url,
            redis_url=redis_url,
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        )
    )
    app.state.webhook_adapter_factory = _factory
    with TestClient(app) as client:
        yield client


def _seed_channel(
    pg_dsn: str,
    *,
    code: str = "mock-marketplace",
    status: str = "active",
    secret: str | None = SECRET,
) -> tuple[str, str]:
    """Insert a tenant + an active channel directly. Returns
    ``(tenant_id, channel_id)`` as strings."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, country_code, plan) VALUES ('T','AZ','free') RETURNING id"
        )
        row = cur.fetchone()
        assert row is not None
        tenant_id = str(row[0])
        config: dict[str, str] = {}
        if secret is not None:
            config["webhook_secret"] = secret
        cur.execute(
            "INSERT INTO channels (tenant_id, code, name, status, config) "
            "VALUES (%s, %s, 'Mock', %s, %s) RETURNING id",
            (tenant_id, code, status, orjson.dumps(config).decode()),
        )
        crow = cur.fetchone()
        assert crow is not None
        channel_id = str(crow[0])
    return tenant_id, channel_id


def _webhook_body(channel_order_id: str = "MOCK-ORD-001") -> bytes:
    """A mock-marketplace order payload — adapter.normalize_webhook expects
    this same shape."""
    return orjson.dumps(
        {
            "channel_order_id": channel_order_id,
            "created_at": "2026-06-04T10:00:00+00:00",
            "currency": "AZN",
            "lines": [
                {"sku": "ABC", "qty": 2, "unit_price_minor": 150, "name": "ABC product"},
            ],
            "subtotal_minor": 300,
            "grand_total_minor": 300,
            "customer_name": "Aysel",
            "status": "pending",
        }
    )


def _channel_orders_count(pg_dsn: str, channel_id: str) -> int:
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM channel_orders WHERE channel_id = %s", (channel_id,))
        row = cur.fetchone()
    return int(row[0]) if row else 0


# ----------------------------------------------------------------
# Happy path + idempotency
# ----------------------------------------------------------------


@pytest.mark.integration
def test_valid_webhook_persists_order(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    body = _webhook_body()
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "received"
    assert payload["channel_order_id"] == "MOCK-ORD-001"
    assert _channel_orders_count(pg_dsn, channel_id) == 1


@pytest.mark.integration
def test_redelivered_webhook_is_idempotent(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    body = _webhook_body("MOCK-ORD-DUP")
    sig = _sign(body)

    first = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": sig, "content-type": "application/json"},
    )
    second = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": sig, "content-type": "application/json"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert _channel_orders_count(pg_dsn, channel_id) == 1


# ----------------------------------------------------------------
# Auth: HMAC failure modes
# ----------------------------------------------------------------


@pytest.mark.integration
def test_missing_signature_is_401(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=_webhook_body(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    assert _channel_orders_count(pg_dsn, channel_id) == 0


@pytest.mark.integration
def test_wrong_signature_is_401(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    body = _webhook_body()
    bad_sig = _sign(body, secret="not-the-real-secret")  # pragma: allowlist secret
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": bad_sig, "content-type": "application/json"},
    )
    assert response.status_code == 401
    assert _channel_orders_count(pg_dsn, channel_id) == 0


# ----------------------------------------------------------------
# Channel lookup failures
# ----------------------------------------------------------------


@pytest.mark.integration
def test_unknown_channel_is_404(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, _ = _seed_channel(pg_dsn, code="mock-marketplace")
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/no-such-channel/webhook",
        content=_webhook_body(),
        headers={"X-Mock-Signature": _sign(_webhook_body())},
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_paused_channel_is_404(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, _ = _seed_channel(pg_dsn, status="paused")
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=_webhook_body(),
        headers={"X-Mock-Signature": _sign(_webhook_body())},
    )
    assert response.status_code == 404


@pytest.mark.integration
def test_channel_without_secret_is_503(app_with_factory: TestClient, pg_dsn: str) -> None:
    """A channel configured without a webhook secret can't verify HMAC;
    surfacing 503 (not 401) tells the operator the config is incomplete."""
    tenant_id, _ = _seed_channel(pg_dsn, secret=None)
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=_webhook_body(),
        headers={"X-Mock-Signature": _sign(_webhook_body())},
    )
    assert response.status_code == 503


# ----------------------------------------------------------------
# Body / wiring failures
# ----------------------------------------------------------------


@pytest.mark.integration
def test_malformed_body_is_400(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, _ = _seed_channel(pg_dsn)
    body = b"not-json"
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_factory_not_wired_is_503(
    migrated_db: None, pg_sqlalchemy_url: str, redis_url: str, pg_dsn: str
) -> None:
    """An app that hasn't been told how to build an adapter for a given
    channel returns 503 (config) rather than blowing up. Lets a deployment
    bring up the API surface before all adapters are registered."""
    app = create_app(
        Settings(
            environment="local",
            database_url=pg_sqlalchemy_url,
            redis_url=redis_url,
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        )
    )
    tenant_id, _ = _seed_channel(pg_dsn)
    with TestClient(app) as client:
        response = client.post(
            f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
            content=_webhook_body(),
            headers={"X-Mock-Signature": _sign(_webhook_body())},
        )
    assert response.status_code == 503
