"""Mock Posnet POS source (AI-2.8).

Two flavours:
* :class:`MockPosnetSource` — in-memory ``PosSourceAdapter`` for fast sync-engine
  unit tests (AI-2.8.1).
* :func:`create_app` + :class:`MockPosnetStore` — an HTTP FastAPI stand-in the
  ``PosnetConnector`` talks to like a real Posnet API (AI-2.8.2).
"""

from __future__ import annotations

from .app import create_app
from .source import MockPosnetSource
from .store import MockPosnetStore

__all__ = ["MockPosnetSource", "MockPosnetStore", "create_app"]
