"""Mock Bazar — a 2nd marketplace stand-in with a different wire shape (Part V V1.1).

Proves the ``ChannelAdapter`` contract + canonical model absorb channel diversity:
:class:`~services.core.app.adapters.mock_bazar.MockBazarAdapter` talks to this
exactly as ``MockMarketplaceAdapter`` talks to mock-marketplace, but the shapes
differ (nested money, list category, different paths/verbs/vocab).
"""

from __future__ import annotations

from .app import create_app
from .store import MockBazarStore

__all__ = ["MockBazarStore", "create_app"]
