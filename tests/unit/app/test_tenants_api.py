"""AI-1.15 — tenant onboarding request schema + endpoint gating (unit, no IO).

The success-path response build and IntegrityError → 409 mapping live in real
integration tests (``test_onboard_endpoint_super_admin_creates_tenant`` and
``test_onboard_endpoint_duplicate_subject_conflicts`` in
``tests/integration/test_onboarding.py``) — running through the full
middleware + DB + RLS stack rather than a monkeypatched stub (AI-2.H3, audit
A5 coverage-paint cleanup).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from libs.auth import Principal
from services.core.app.api.deps import get_principal, get_tenant_session
from services.core.app.api.v1.tenants import TenantOnboardRequest
from services.core.app.config import Settings
from services.core.app.main import create_app

# ---- request schema ----


@pytest.mark.unit
def test_request_normalises_country_and_email() -> None:
    req = TenantOnboardRequest(
        name="Acme", country_code="az", admin_email="Owner@Acme.AZ", admin_subject="kc-1"
    )
    assert req.country_code == "AZ"
    assert req.admin_email == "owner@acme.az"
    assert req.plan == "free"  # default


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},  # blank name
        {"country_code": "AZE"},  # not alpha-2
        {"admin_email": "no-at-sign"},  # not an email
        {"admin_subject": ""},  # blank subject
        {"extra_field": "x"},  # extra=forbid
    ],
)
def test_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    base: dict[str, Any] = {
        "name": "Acme",
        "country_code": "AZ",
        "admin_email": "a@acme.io",
        "admin_subject": "kc-1",
    }
    with pytest.raises(ValidationError):
        TenantOnboardRequest(**{**base, **overrides})


# ---- endpoint gating (super_admin only) ----


@pytest.mark.unit
def test_onboard_forbidden_for_non_super_admin() -> None:
    app = create_app(
        Settings(
            environment="local",
            database_url="postgresql+psycopg://u@localhost/x",
            redis_url="redis://localhost:6379/0",
            eventbus_enabled=False,
            rate_limit_storage_uri="memory://",
        )
    )
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="kc-cashier", username="c", email="c@x.io", roles=frozenset({"cashier"})
    )
    app.dependency_overrides[get_tenant_session] = lambda: None  # never reached (gate fires first)

    with TestClient(app) as client:
        response = client.post(
            "/v1/tenants",
            json={
                "name": "Acme",
                "country_code": "AZ",
                "admin_email": "a@acme.io",
                "admin_subject": "kc-admin",
            },
        )
    assert response.status_code == 403
