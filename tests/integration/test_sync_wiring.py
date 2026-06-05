"""AI H6 (ADR-0020) — sync engine production wiring.

``create_app`` wires the SyncDispatcher + a registry-driven adapter factory when
``sync_enabled`` is set, so a deployed app processes outbox events into channel
pushes. These tests pin the wiring without standing the app up (no lifespan, so
no DB/Redis): they inspect ``app.state`` and exercise the factory directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar
from uuid import uuid4

import pytest

from libs.adapter import AdapterCapabilities, AdapterNotFoundError, clear_registry, get_adapter
from services.core.app.adapters.mock_marketplace import MockMarketplaceAdapter
from services.core.app.adapters.mock_marketplace.adapter import CODE as MOCK_CODE
from services.core.app.config import Settings
from services.core.app.infrastructure.db.models import Channel
from services.core.app.main import create_app
from services.core.app.sync.wiring import (
    build_adapter,
    build_adapter_factory,
    build_webhook_adapter_factory,
    register_builtin_adapters,
)


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    clear_registry()
    yield
    clear_registry()


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "local",
        "mock_marketplace_base_url": "http://mock-default:9200",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _channel(*, code: str = MOCK_CODE, config: dict[str, object] | None = None) -> Channel:
    return Channel(tenant_id=uuid4(), code=code, name=code, status="active", config=config or {})


# ----------------------------------------------------------------
# Registry
# ----------------------------------------------------------------


@pytest.mark.unit
def test_register_builtin_adapters_registers_mock() -> None:
    register_builtin_adapters()
    assert get_adapter(MOCK_CODE) is MockMarketplaceAdapter


@pytest.mark.unit
def test_register_builtin_adapters_is_idempotent() -> None:
    register_builtin_adapters()
    register_builtin_adapters()  # no AdapterAlreadyRegisteredError
    assert get_adapter(MOCK_CODE) is MockMarketplaceAdapter


# ----------------------------------------------------------------
# from_channel + build_adapter
# ----------------------------------------------------------------


@pytest.mark.unit
def test_from_channel_uses_config_base_url() -> None:
    adapter = MockMarketplaceAdapter.from_channel(
        _channel(config={"base_url": "http://channel-specific"}), settings=_settings()
    )
    assert isinstance(adapter, MockMarketplaceAdapter)
    assert adapter._config.base_url == "http://channel-specific"


@pytest.mark.unit
def test_from_channel_falls_back_to_settings_base_url() -> None:
    adapter = MockMarketplaceAdapter.from_channel(_channel(config={}), settings=_settings())
    assert adapter._config.base_url == "http://mock-default:9200"


@pytest.mark.unit
def test_build_adapter_resolves_registered_mock() -> None:
    register_builtin_adapters()
    adapter = build_adapter(_channel(), _settings())
    assert isinstance(adapter, MockMarketplaceAdapter)


@pytest.mark.unit
def test_build_adapter_unregistered_code_raises() -> None:
    with pytest.raises(AdapterNotFoundError):
        build_adapter(_channel(code="no-such-channel"), _settings())


@pytest.mark.unit
def test_build_adapter_registered_without_from_channel_raises() -> None:
    """A registered adapter that lacks ``from_channel`` is not production-wireable
    yet — surfaced clearly rather than crashing at first dispatch."""

    class _NoFromChannel:
        capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
            code="nofc", name="No From Channel", auth_kind="none"
        )

    from libs.adapter import register_adapter

    register_adapter("nofc", _NoFromChannel)  # type: ignore[arg-type]
    with pytest.raises(AdapterNotFoundError, match="from_channel"):
        build_adapter(_channel(code="nofc"), _settings())


@pytest.mark.unit
async def test_async_and_sync_factories_build_mock() -> None:
    register_builtin_adapters()
    settings = _settings()
    async_factory = build_adapter_factory(settings)
    sync_factory = build_webhook_adapter_factory(settings)

    from_async = await async_factory(_channel())
    from_sync = sync_factory(_channel())
    assert isinstance(from_async, MockMarketplaceAdapter)
    assert isinstance(from_sync, MockMarketplaceAdapter)


# ----------------------------------------------------------------
# create_app wiring
# ----------------------------------------------------------------


@pytest.mark.unit
def test_create_app_sync_enabled_wires_webhook_factory() -> None:
    app = create_app(_settings(sync_enabled=True))
    factory = getattr(app.state, "webhook_adapter_factory", None)
    assert factory is not None
    # The wired factory builds a real adapter for a mock channel.
    assert isinstance(factory(_channel()), MockMarketplaceAdapter)


@pytest.mark.unit
def test_create_app_sync_disabled_skips_wiring() -> None:
    app = create_app(_settings(sync_enabled=False))
    assert getattr(app.state, "webhook_adapter_factory", None) is None


@pytest.mark.unit
def test_create_app_injected_handler_skips_wiring() -> None:
    """An explicitly injected event_handler (the test path) wins — production
    wiring only kicks in when no handler is supplied."""

    async def _stub_handler(session: object, event: object) -> None:
        return None

    app = create_app(_settings(sync_enabled=True), event_handler=_stub_handler)  # type: ignore[arg-type]
    assert getattr(app.state, "webhook_adapter_factory", None) is None
