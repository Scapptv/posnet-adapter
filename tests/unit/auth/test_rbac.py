"""AI-1.8 — require_role / require_permission, wildcards, super_admin bypass."""

from __future__ import annotations

import pytest

from libs.auth import Principal, has_permission, require_permission, require_role
from libs.common import ForbiddenError


def _principal(*roles: str) -> Principal:
    return Principal(subject="s-1", username="u", email="u@posnet.test", roles=frozenset(roles))


@pytest.mark.unit
def test_require_role_allows_match() -> None:
    require_role(_principal("cashier"), "cashier", "store_manager")  # no raise


@pytest.mark.unit
def test_require_role_denies_when_absent() -> None:
    with pytest.raises(ForbiddenError):
        require_role(_principal("clerk"), "cashier")


@pytest.mark.unit
def test_super_admin_bypasses_role_check() -> None:
    require_role(_principal("super_admin"), "cashier")  # no raise


@pytest.mark.unit
def test_cashier_can_sell_but_not_write_catalog() -> None:
    cashier = _principal("cashier")
    assert has_permission(cashier, "sale", "write")
    assert not has_permission(cashier, "catalog", "write")


@pytest.mark.unit
def test_tenant_admin_has_wildcard() -> None:
    assert has_permission(_principal("tenant_admin"), "anything", "delete")


@pytest.mark.unit
def test_unknown_role_grants_nothing() -> None:
    assert not has_permission(_principal("ghost"), "catalog", "read")


@pytest.mark.unit
def test_require_permission_denies() -> None:
    with pytest.raises(ForbiddenError):
        require_permission(_principal("clerk"), "sale", "write")


@pytest.mark.unit
def test_require_permission_allows_super_admin() -> None:
    require_permission(_principal("super_admin"), "billing", "delete")  # no raise
