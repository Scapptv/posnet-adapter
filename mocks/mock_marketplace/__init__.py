"""Mock marketplace service (AI-2.5.3, roadmap §17.5).

A standalone FastAPI app that mimics a Birmarket/Trendyol-style seller API
just enough to drive the channel-adapter contract end-to-end. Real adapter
swap-ready: the same surface (POST /listings, PATCH stock/price, GET orders,
POST ack) lands on the real partner with credentials swapped in.
"""

from __future__ import annotations

from .app import create_app
from .store import MockStore

__all__ = ["MockStore", "create_app"]
