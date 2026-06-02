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

# psycopg async refuses the Windows ProactorEventLoop. The fixture below covers
# pytest-asyncio's loops; this global set also covers loops we don't own (e.g.
# Starlette TestClient's portal thread). Prod runs on Linux, so this is dev-only.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Force the selector loop for pytest-asyncio on Windows (psycopg async)."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
