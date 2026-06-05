"""Posnet POS connector (AI-2.8.2, ADR-0021).

Concrete :class:`~libs.pos_source.PosSourceAdapter` for the external Posnet POS
over HTTP. The POS-side counterpart of :mod:`...adapters.mock_marketplace`:
talks to :mod:`mocks.mock_posnet` today, swaps to the live Posnet API by
base-URL once its interface is known. Real-shaped (httpx + error classification)
so the swap touches nothing upstream.
"""

from __future__ import annotations

from .connector import PosnetConfig, PosnetConnector

__all__ = ["PosnetConfig", "PosnetConnector"]
