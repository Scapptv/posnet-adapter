"""Production wiring for the sync engine (H6, ADR-0020).

The dispatcher (AI-2.5.2) and the webhook ingress (AI-2.5.4) both take an
*adapter factory* — a callable that turns a :class:`Channel` row into a
configured :class:`~libs.adapter.ChannelAdapter`. In tests a stub factory is
injected; for a deployable service this module builds the real one:
``get_adapter(channel.code)`` resolves the registered adapter class, and the
adapter's ``from_channel`` classmethod constructs an instance from the channel's
config + app settings.

``create_app`` calls :func:`register_builtin_adapters` + :func:`build_dispatcher`
when ``settings.sync_enabled`` is set, so an event consumed off the outbox fans
out to every active channel's adapter — the whole AI-2.5 machinery (dispatch,
reconcile, observability) goes live (H6 — "işlək deploy edilə bilən servis").
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from libs.adapter import AdapterNotFoundError, ChannelAdapter, get_adapter, register_adapter

from ..config import Settings
from ..infrastructure.db.models import Channel
from .dispatcher import AdapterFactory, SyncDispatcher

WebhookAdapterFactory = Callable[[Channel], ChannelAdapter]
"""The *sync* factory shape the webhook ingress uses (``adapter = factory(channel)``);
the dispatcher's :data:`~services.core.app.sync.dispatcher.AdapterFactory` is the
async counterpart. Both wrap :func:`build_adapter`."""


def register_builtin_adapters() -> None:
    """Register the adapters that ship with the app.

    The mock marketplace is registered for dev/demo — it speaks the real channel
    contract against a stand-in server. Real adapters self-register on import
    once they exist (with credentials, post-G-V). Idempotent (``register_adapter``
    no-ops on the same class), so calling it on every ``create_app`` is safe.
    """
    from ..adapters.mock_marketplace import MockMarketplaceAdapter

    # MockMarketplaceAdapter structurally satisfies the ChannelAdapter Protocol
    # (proven by the contract suite); mypy can't infer type[Concrete] -> type[Protocol].
    register_adapter(
        MockMarketplaceAdapter.capabilities.code,
        cast("type[ChannelAdapter]", MockMarketplaceAdapter),
    )


def build_adapter(channel: Channel, settings: Settings) -> ChannelAdapter:
    """Resolve ``channel.code`` to its registered adapter and construct it.

    Raises :class:`~libs.adapter.AdapterNotFoundError` if no adapter is
    registered for the code, or if the registered adapter lacks a
    ``from_channel`` constructor (registered but not production-wireable yet).
    """
    cls = get_adapter(channel.code)
    from_channel = getattr(cls, "from_channel", None)
    if from_channel is None:
        raise AdapterNotFoundError(
            f"adapter {channel.code!r} has no from_channel constructor "
            "(registered but not production-wireable)"
        )
    adapter: ChannelAdapter = from_channel(channel, settings=settings)
    return adapter


def build_adapter_factory(settings: Settings) -> AdapterFactory:
    """Async adapter factory for the dispatcher (``await factory(channel)``)."""

    async def _factory(channel: Channel) -> ChannelAdapter:
        return build_adapter(channel, settings)

    return _factory


def build_webhook_adapter_factory(settings: Settings) -> WebhookAdapterFactory:
    """Sync adapter factory for the webhook ingress (``factory(channel)``)."""

    def _factory(channel: Channel) -> ChannelAdapter:
        return build_adapter(channel, settings)

    return _factory


def build_dispatcher(settings: Settings) -> SyncDispatcher:
    """The outbox-event handler that fans out to channel adapters (H6)."""
    return SyncDispatcher(adapter_factory=build_adapter_factory(settings))
