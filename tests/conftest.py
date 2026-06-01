"""Posnet test configuration (root).

- Unit tests are fast (no IO): @pytest.mark.unit.
- Integration tests use real Postgres/Redis via testcontainers
  (@pytest.mark.integration, see tests/integration/conftest.py).
- Fast local run: ``pytest -m "not integration"``.

Shared fixtures (per-test DB rollback, Redis flush, Keycloak token mock)
will be added here once DB/auth land (AI-1.5+).
"""

from __future__ import annotations
