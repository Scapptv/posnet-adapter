"""AI-1.8 — Principal role helpers."""

from __future__ import annotations

import pytest

from libs.auth import Principal


def _principal(*roles: str) -> Principal:
    return Principal(subject="s-1", username="u", email="u@posnet.test", roles=frozenset(roles))


@pytest.mark.unit
def test_has_role() -> None:
    principal = _principal("cashier", "clerk")
    assert principal.has_role("cashier")
    assert not principal.has_role("tenant_admin")


@pytest.mark.unit
def test_is_super_admin() -> None:
    assert _principal("super_admin").is_super_admin
    assert not _principal("tenant_admin").is_super_admin
