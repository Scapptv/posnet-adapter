"""Mock marketplace channel adapter (AI-2.5.3).

Concrete :class:`~libs.adapter.ChannelAdapter` for the
:mod:`mocks.mock-marketplace` service. Used as the canary in adapter contract
tests and as the engine end of E2E flows (AI-2.5.5) — real marketplace
adapters (Trendyol, Birmarket) follow this template.
"""

from __future__ import annotations

from .adapter import MockMarketplaceAdapter, MockMarketplaceConfig

__all__ = ["MockMarketplaceAdapter", "MockMarketplaceConfig"]
