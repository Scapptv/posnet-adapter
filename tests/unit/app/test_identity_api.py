"""AI-1.16 — identity request schemas + require_tenant dependency (unit, no IO)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from libs.common import ForbiddenError
from services.core.app.api.deps import require_tenant
from services.core.app.api.v1.roles import RoleCreateRequest
from services.core.app.api.v1.users import AssignRoleRequest, UserCreateRequest

# ---- schemas ----


@pytest.mark.unit
def test_user_request_normalises_email() -> None:
    req = UserCreateRequest(email="Admin@T.AZ")
    assert req.email == "admin@t.az"
    assert req.external_subject is None
    assert req.phone is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [{"email": "no-at-sign"}, {"email": "a@b.c", "extra": "x"}],
)
def test_user_request_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        UserCreateRequest(**{"email": "a@acme.io", **overrides})


@pytest.mark.unit
def test_role_request_accepts_permissions() -> None:
    req = RoleCreateRequest(
        name="manager", permissions=[{"resource": "catalog", "action": "write"}]
    )
    assert req.permissions[0].resource == "catalog"
    assert req.permissions[0].action == "write"


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [{"name": ""}, {"name": "r", "permissions": [{"resource": "catalog"}]}],
    ids=["blank-name", "permission-missing-action"],
)
def test_role_request_rejects_invalid(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RoleCreateRequest(**kwargs)


@pytest.mark.unit
def test_assign_request_defaults_store_to_none() -> None:
    req = AssignRoleRequest(role_id=uuid4())
    assert req.store_id is None


# ---- require_tenant ----


def _request_with_tenant(tenant_id: object) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.tenant_id = tenant_id
    return request


@pytest.mark.unit
async def test_require_tenant_returns_resolved_id() -> None:
    tenant_id = uuid4()
    request = _request_with_tenant(tenant_id)
    assert await require_tenant(request, _session=None) == tenant_id  # type: ignore[arg-type]


@pytest.mark.unit
async def test_require_tenant_rejects_missing_tenant() -> None:
    request = _request_with_tenant(None)
    with pytest.raises(ForbiddenError):
        await require_tenant(request, _session=None)  # type: ignore[arg-type]
