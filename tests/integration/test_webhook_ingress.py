"""AI-2.5.4 + AI-2.5.5 — webhook ingress end-to-end.

Drives ``POST /v1/channels/{tenant_id}/{code}/webhook`` against the real app
with a stub adapter factory pointing at :class:`MockMarketplaceAdapter` (its
HTTP client wired to a :class:`httpx.MockTransport` so the best-effort ack
never touches the network). Covers the contract:

* valid HMAC + sellable SKU → ``200`` ``status="reserved"``, stock reserved.
* redelivered webhook (same channel_order_id) → ``200`` ``status="duplicate"``,
  no second row, stock reserved only once.
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
from collections.abc import Callable, Iterator, Sequence
from typing import cast
from uuid import UUID

import httpx
import orjson
import psycopg
import pytest
from fastapi.testclient import TestClient

from libs.adapter import AdapterRetryableError, ChannelAdapter
from libs.canonical_model import CanonicalOrder, CanonicalProduct
from libs.pos_source import PosSourceAdapter, PosSourceCapabilities
from mocks.mock_posnet import MockPosnetSource
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


def _ack_ok(_request: httpx.Request) -> httpx.Response:
    """Always-200 so the webhook's best-effort ack succeeds without a socket."""
    return httpx.Response(200, json={"status": "ok"})


def _adapter() -> ChannelAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_ack_ok), base_url="http://mock")
    return cast(
        ChannelAdapter,
        MockMarketplaceAdapter(MockMarketplaceConfig(base_url="http://mock"), client=client),
    )


def _factory(_channel: Channel) -> ChannelAdapter:
    return _adapter()


def _seed_sellable(pg_dsn: str, tenant_id: str, *, sku: str, qty: int) -> None:
    """Insert a product + variant + online warehouse + stock so an order for
    ``sku`` can reserve. Direct SQL — the reservation path is what's under test."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO products (tenant_id, name) VALUES (%s, 'P') RETURNING id", (tenant_id,)
        )
        product = cur.fetchone()
        assert product is not None
        cur.execute(
            "INSERT INTO variants (tenant_id, product_id, sku, base_price_minor) "
            "VALUES (%s, %s, %s, 500) RETURNING id",
            (tenant_id, product[0], sku),
        )
        variant = cur.fetchone()
        assert variant is not None
        cur.execute(
            "INSERT INTO warehouses (tenant_id, name) VALUES (%s, 'W') RETURNING id", (tenant_id,)
        )
        warehouse = cur.fetchone()
        assert warehouse is not None
        cur.execute(
            "INSERT INTO inventory (tenant_id, variant_id, warehouse_id, qty) VALUES (%s, %s, %s, %s)",
            (tenant_id, variant[0], warehouse[0], qty),
        )


def _reserved_qty(pg_dsn: str, sku: str) -> int:
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT i.reserved_qty FROM inventory i "
            "JOIN variants v ON v.id = i.variant_id WHERE v.sku = %s",
            (sku,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else -1


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
def test_valid_webhook_reserves_order(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
    body = _webhook_body()  # one line: sku ABC, qty 2
    response = app_with_factory.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "reserved"
    assert payload["channel_order_id"] == "MOCK-ORD-001"
    assert _channel_orders_count(pg_dsn, channel_id) == 1
    assert _reserved_qty(pg_dsn, "ABC") == 2


@pytest.mark.integration
def test_redelivered_webhook_is_idempotent(app_with_factory: TestClient, pg_dsn: str) -> None:
    tenant_id, channel_id = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
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
    assert first.json()["status"] == "reserved"
    assert second.json()["status"] == "duplicate"
    assert _channel_orders_count(pg_dsn, channel_id) == 1
    assert _reserved_qty(pg_dsn, "ABC") == 2  # reserved once, not twice


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


# ----------------------------------------------------------------
# AI-2.8.3 — POS write-back (a reserved order is pushed back into Posnet)
# ----------------------------------------------------------------


def _pos_factory(pos: PosSourceAdapter) -> Callable[[UUID], PosSourceAdapter]:
    """A pos_source_factory that hands the same POS connector to every tenant."""

    def _factory(_tenant_id: UUID) -> PosSourceAdapter:
        return pos

    return _factory


class _FailingPos:
    """A POS whose write-back always fails — proves best-effort isolation
    (a POS hiccup must not fail the webhook or undo the reservation)."""

    capabilities = PosSourceCapabilities(
        code="posnet", name="Posnet", supports_pull_catalog=True, supports_push_order=True
    )

    async def pull_catalog(self) -> Sequence[CanonicalProduct]:  # pragma: no cover - unused
        return []

    async def push_order(self, order: CanonicalOrder) -> None:
        raise AdapterRetryableError("posnet unavailable")


class _ReadOnlyPos:
    """A POS that can't accept order write-back (capability off)."""

    capabilities = PosSourceCapabilities(
        code="posnet",
        name="Posnet (read-only)",
        supports_pull_catalog=True,
        supports_push_order=False,
    )

    def __init__(self) -> None:
        self.pushed: list[CanonicalOrder] = []

    async def pull_catalog(self) -> Sequence[CanonicalProduct]:  # pragma: no cover - unused
        return []

    async def push_order(self, order: CanonicalOrder) -> None:  # pragma: no cover - gated off
        self.pushed.append(order)


def _post_order(client: TestClient, tenant_id: str, body: bytes) -> httpx.Response:
    return client.post(
        f"/v1/channels/{tenant_id}/mock-marketplace/webhook",
        content=body,
        headers={"X-Mock-Signature": _sign(body), "content-type": "application/json"},
    )


@pytest.mark.integration
def test_reserved_order_is_written_back_to_pos(app_with_factory: TestClient, pg_dsn: str) -> None:
    """The crown-jewel tail (§17.7): a marketplace order that reserves stock is
    pushed into the POS (Posnet) — the source of truth — as a canonical order."""
    tenant_id, _ = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
    pos = MockPosnetSource()
    app_with_factory.app.state.pos_source_factory = _pos_factory(pos)

    response = _post_order(app_with_factory, tenant_id, _webhook_body())

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reserved"
    assert len(pos.pushed_orders) == 1
    written = pos.pushed_orders[0]
    assert written.channel_order_id == "MOCK-ORD-001"
    assert written.lines[0].sku == "ABC"
    assert written.lines[0].qty == 2


@pytest.mark.integration
def test_rejected_order_is_not_written_back_to_pos(
    app_with_factory: TestClient, pg_dsn: str
) -> None:
    """A rejected order reserved nothing — there's no sale to record in the POS."""
    tenant_id, _ = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=1)  # order wants 2 -> oversold
    pos = MockPosnetSource()
    app_with_factory.app.state.pos_source_factory = _pos_factory(pos)

    response = _post_order(app_with_factory, tenant_id, _webhook_body())

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert pos.pushed_orders == []


@pytest.mark.integration
def test_pos_write_back_failure_does_not_fail_webhook(
    app_with_factory: TestClient, pg_dsn: str
) -> None:
    """A POS write-back failure is best-effort: the webhook still succeeds and
    the reservation stays durable (reconciliation/retry catches the miss)."""
    tenant_id, _ = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
    app_with_factory.app.state.pos_source_factory = _pos_factory(_FailingPos())

    response = _post_order(app_with_factory, tenant_id, _webhook_body())

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reserved"
    assert _reserved_qty(pg_dsn, "ABC") == 2  # durable despite the POS failure


@pytest.mark.integration
def test_read_only_pos_is_skipped(app_with_factory: TestClient, pg_dsn: str) -> None:
    """A POS that doesn't support order write-back (capability off) is skipped —
    push_order is never called."""
    tenant_id, _ = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
    pos = _ReadOnlyPos()
    app_with_factory.app.state.pos_source_factory = _pos_factory(pos)

    response = _post_order(app_with_factory, tenant_id, _webhook_body())

    assert response.status_code == 200
    assert response.json()["status"] == "reserved"
    assert pos.pushed == []


@pytest.mark.integration
def test_pos_write_back_not_duplicated_on_redelivery(
    app_with_factory: TestClient, pg_dsn: str
) -> None:
    """A redelivered webhook short-circuits to ``duplicate`` before reserving —
    so the POS is written exactly once, never twice."""
    tenant_id, _ = _seed_channel(pg_dsn)
    _seed_sellable(pg_dsn, tenant_id, sku="ABC", qty=10)
    pos = MockPosnetSource()
    app_with_factory.app.state.pos_source_factory = _pos_factory(pos)
    body = _webhook_body("MOCK-ORD-PUSH-DUP")

    first = _post_order(app_with_factory, tenant_id, body)
    second = _post_order(app_with_factory, tenant_id, body)

    assert first.json()["status"] == "reserved"
    assert second.json()["status"] == "duplicate"
    assert len(pos.pushed_orders) == 1
