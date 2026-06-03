"""AI-1.15 — tenant onboarding request schema + endpoint gating (unit, no IO)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from libs.auth import Principal
from libs.common import ConflictError
from services.core.app.api.deps import get_principal, get_tenant_session
from services.core.app.api.v1 import tenants as tenants_module
from services.core.app.api.v1.tenants import TenantOnboardRequest
from services.core.app.config import Settings
from services.core.app.domain.onboarding import TenantOnboarded
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


@pytest.mark.unit
async def test_onboard_endpoint_builds_response(monkeypatch: pytest.MonkeyPatch) -> None:
    # Call the route function in the main thread (coverage can't trace the
    # post-await response build under TestClient's greenlet) with onboard_tenant
    # stubbed, so the success-path response mapping is covered deterministically.
    tenant_id, user_id = uuid4(), uuid4()

    async def _fake_onboard(_session: object, **kwargs: str) -> TenantOnboarded:
        return TenantOnboarded(
            tenant_id=tenant_id, admin_user_id=user_id, name=kwargs["name"], status="active"
        )

    monkeypatch.setattr(tenants_module, "onboard_tenant", _fake_onboard)
    response = await tenants_module.onboard(
        TenantOnboardRequest(
            name="Acme", country_code="AZ", admin_email="a@acme.io", admin_subject="kc-1"
        ),
        _admin=Principal(
            subject="s", username="u", email="e@x.io", roles=frozenset({"super_admin"})
        ),
        session=None,  # type: ignore[arg-type]  # the stub ignores it
    )
    assert response.tenant_id == tenant_id
    assert response.admin_user_id == user_id
    assert response.name == "Acme"
    assert response.status == "active"


@pytest.mark.unit
async def test_onboard_endpoint_maps_integrity_error_to_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise(_session: object, **_kwargs: str) -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(tenants_module, "onboard_tenant", _raise)
    with pytest.raises(ConflictError):
        await tenants_module.onboard(
            TenantOnboardRequest(
                name="Acme", country_code="AZ", admin_email="a@acme.io", admin_subject="kc-1"
            ),
            _admin=Principal(
                subject="s", username="u", email="e@x.io", roles=frozenset({"super_admin"})
            ),
            session=None,  # type: ignore[arg-type]
        )
