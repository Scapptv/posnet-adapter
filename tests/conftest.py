"""Posnet test configuration (root).

- Unit tests are fast (no IO): @pytest.mark.unit.
- Integration tests use real Postgres/Redis via testcontainers
  (@pytest.mark.integration, see tests/integration/conftest.py).
- Fast local run: ``pytest -m "not integration"``.

Shared fixtures (per-test DB rollback, Redis flush, Keycloak token mock)
will be added here once DB/auth land (AI-1.5+).
"""

from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """psycopg async refuses the Windows ProactorEventLoop; force the selector
    loop so local integration tests can reach Postgres (prod runs on Linux)."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
