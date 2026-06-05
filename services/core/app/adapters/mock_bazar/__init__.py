"""Mock Bazar channel adapter (Part V V1.1) — the 2nd concrete ChannelAdapter.

Same ``libs.adapter.ChannelAdapter`` contract as ``mock_marketplace``, against a
differently-shaped channel (:mod:`mocks.mock_bazar`) — the proof that adding a
channel costs one adapter + one contract test. Real Birmarket/Trendyol follow
this template once partner credentials arrive (D-002).
"""

from __future__ import annotations

from .adapter import MockBazarAdapter, MockBazarConfig

__all__ = ["MockBazarAdapter", "MockBazarConfig"]
