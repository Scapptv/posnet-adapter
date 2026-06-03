"""AI-1.9.3 — auth dependencies, RBAC gating, and scope helpers (unit, no IO)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from libs.auth import Principal
from libs.common import AuthError, ForbiddenError
from services.core.app.api.deps import (
    _bearer_token,
    get_principal,
    get_tenant_session,
    get_token_verifier,
    requires_permission,
    requires_role,
)
from services.core.app.config import Settings
from services.core.app.infrastructure.db.tenant import apply_tenant_scope, resolve_tenant_id
from services.core.app.main import create_app
from services.core.app.security import build_auth_config


def _principal(*roles: str, subject: str = "kc-sub") -> Principal:
    return Principal(subject=subject, username="u", email="u@posnet.test", roles=frozenset(roles))


class _FakeVerifier:
    """Stand-in for TokenVerifier — returns a fixed principal or raises."""

    def __init__(
        self, *, principal: Principal | None = None, error: Exception | None = None
    ) -> None:
        self._principal = principal
        self._error = error

    async def verify(self, token: str) -> Principal:
        if self._error is not None:
            raise self._error
        assert self._principal is not None
        return self._principal


def _app() -> FastAPI:
    app = create_app(
        Settings(
            environment="local",
            database_url="postgresql+psycopg://u@localhost/x",
            redis_url="redis://localhost:6379/0",
            rate_limit_storage_uri="memory://",  # isolated per-app counter
            eventbus_enabled=False,  # no pgmq in unit tests
        )
    )

    @app.get("/me")
    async def _me(principal: Principal = Depends(get_principal)) -> dict[str, str]:
        return {"sub": principal.subject}

    @app.get("/gated/role", dependencies=[Depends(requires_role("tenant_admin"))])
    async def _role() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/gated/perm", dependencies=[Depends(requires_permission("catalog", "write"))])
    async def _perm() -> dict[str, bool]:
        return {"ok": True}

    return app


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


# ---- bearer extraction (all branches) ----


@pytest.mark.unit
def test_bearer_token_valid() -> None:
    assert _bearer_token(_request({"Authorization": "Bearer abc.def"})) == "abc.def"


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Token abc"}, {"Authorization": "Bearer    "}],
    ids=["missing", "wrong-scheme", "empty-token"],
)
def test_bearer_token_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(AuthError):
        _bearer_token(_request(headers))


# ---- get_principal wiring (verifier success / failure) ----


@pytest.mark.unit
def test_missing_header_is_401() -> None:
    with TestClient(_app()) as client:
        response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.unit
def test_valid_token_yields_principal() -> None:
    app = _app()
    app.dependency_overrides[get_token_verifier] = lambda: _FakeVerifier(
        principal=_principal("clerk", subject="kc-42")
    )
    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    assert response.json() == {"sub": "kc-42"}


@pytest.mark.unit
def test_verifier_rejection_is_401() -> None:
    app = _app()
    app.dependency_overrides[get_token_verifier] = lambda: _FakeVerifier(error=AuthError("nope"))
    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401


# ---- RBAC gating via Depends ----


@pytest.mark.unit
@pytest.mark.parametrize(
    "roles,status",
    [(["tenant_admin"], 200), (["super_admin"], 200), (["cashier"], 403)],
)
def test_requires_role_gate(roles: list[str], status: int) -> None:
    app = _app()
    app.dependency_overrides[get_principal] = lambda: _principal(*roles)
    with TestClient(app) as client:
        response = client.get("/gated/role")
    assert response.status_code == status


@pytest.mark.unit
@pytest.mark.parametrize(
    "roles,status",
    [(["clerk"], 200), (["tenant_admin"], 200), (["cashier"], 403)],
)
def test_requires_permission_gate(roles: list[str], status: int) -> None:
    app = _app()
    app.dependency_overrides[get_principal] = lambda: _principal(*roles)
    with TestClient(app) as client:
        response = client.get("/gated/perm")
    assert response.status_code == status


# ---- settings -> AuthConfig mapping ----


@pytest.mark.unit
def test_build_auth_config_from_settings() -> None:
    cfg = build_auth_config(
        Settings(
            keycloak_url="http://kc:8080/",  # trailing slash tolerated
            keycloak_realm="posnet",
            keycloak_audiences="api-gateway, account",
        )
    )
    assert cfg.issuer == "http://kc:8080/realms/posnet"
    assert cfg.jwks_url == "http://kc:8080/realms/posnet/protocol/openid-connect/certs"
    assert cfg.audiences == ("api-gateway", "account")


# ---- apply_tenant_scope identity guard (no session touched) ----


class _NoSession:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("execute must not be called when the role is invalid")


@pytest.mark.unit
async def test_apply_tenant_scope_rejects_bad_role() -> None:
    with pytest.raises(ValueError, match="invalid app DB role"):
        await apply_tenant_scope(_NoSession(), uuid.uuid4(), role="evil; DROP TABLE users")  # type: ignore[arg-type]


# ---- resolve_tenant_id + get_tenant_session logic (in-process fakes) ----
#
# The integration suite proves the real DB/RLS behaviour, but coverage cannot
# trace lines resumed after SQLAlchemy's async greenlet switch. These fakes run
# the same branches in the main thread so the security-critical resolution +
# scoping logic is unit-covered too.


class _FakeResult:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def first(self) -> tuple[object, ...] | None:
        return self._row


class _FakeTx:
    async def __aenter__(self) -> _FakeTx:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    def __init__(self, row: tuple[object, ...] | None = None) -> None:
        self.row = row
        self.statements: list[str] = []

    async def execute(self, statement: object, params: object = None) -> _FakeResult:
        self.statements.append(str(statement))
        return _FakeResult(self.row)

    def begin(self) -> _FakeTx:
        return _FakeTx()

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _request_for(session: _FakeSession) -> Request:
    # Both pools resolve to the same fake session; the app pool serves regular
    # callers and the system pool serves super_admin (ADR-0017).
    app = SimpleNamespace(
        state=SimpleNamespace(
            sessionmaker=lambda: session,
            system_sessionmaker=lambda: session,
            settings=Settings(),
        )
    )
    return Request({"type": "http", "app": app, "state": {}})


@pytest.mark.unit
async def test_resolve_tenant_id_found() -> None:
    tenant_id = uuid.uuid4()
    got = await resolve_tenant_id(_FakeSession(row=(tenant_id,)), subject="kc-1")  # type: ignore[arg-type]
    assert got == tenant_id


@pytest.mark.unit
async def test_resolve_tenant_id_not_found() -> None:
    got = await resolve_tenant_id(_FakeSession(row=None), subject="kc-ghost")  # type: ignore[arg-type]
    assert got is None


@pytest.mark.unit
async def test_get_tenant_session_scopes_to_resolved_tenant() -> None:
    tenant_id = uuid.uuid4()
    session = _FakeSession(row=(tenant_id,))
    request = _request_for(session)
    agen = get_tenant_session(request, principal=_principal("tenant_admin"))

    yielded = await agen.__anext__()
    assert yielded is session
    assert request.state.tenant_id == tenant_id
    assert any("SET LOCAL ROLE" in stmt for stmt in session.statements)
    with pytest.raises(StopAsyncIteration):  # resume past yield -> clean teardown
        await agen.__anext__()


@pytest.mark.unit
async def test_get_tenant_session_super_admin_runs_unscoped() -> None:
    session = _FakeSession(row=None)
    request = _request_for(session)
    agen = get_tenant_session(request, principal=_principal("super_admin"))

    yielded = await agen.__anext__()
    assert yielded is session
    assert request.state.tenant_id is None
    assert session.statements == []  # no role switch, no GUC -> cross-tenant
    with pytest.raises(StopAsyncIteration):  # resume past yield -> hits the early return
        await agen.__anext__()


@pytest.mark.unit
async def test_get_tenant_session_forbids_unknown_subject() -> None:
    session = _FakeSession(row=None)
    request = _request_for(session)
    agen = get_tenant_session(request, principal=_principal("cashier"))

    with pytest.raises(ForbiddenError):
        await agen.__anext__()
