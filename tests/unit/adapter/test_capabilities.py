"""Unit tests for AdapterCapabilities (AI-2.5.1)."""

from __future__ import annotations

import pytest

from libs.adapter import AdapterCapabilities


@pytest.mark.unit
def test_capabilities_defaults() -> None:
    caps = AdapterCapabilities(code="x", name="X", auth_kind="api_key")
    assert caps.supports_push_listing is True
    assert caps.supports_push_stock is True
    assert caps.supports_push_price is True
    assert caps.supports_pull_orders is False
    assert caps.supports_webhook_orders is False
    assert caps.rate_limit_rps == 1
    assert caps.rate_limit_burst == 1
    assert caps.tags == frozenset()


@pytest.mark.unit
def test_capabilities_is_frozen() -> None:
    """Capabilities are class-level facts; runtime mutation is a bug."""
    caps = AdapterCapabilities(code="x", name="X", auth_kind="api_key")
    with pytest.raises((AttributeError, Exception)):
        caps.code = "y"  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    "code",
    ["birmarket", "trendyol", "wolt-food", "test_channel", "AZ1"],
)
def test_capabilities_accepts_valid_codes(code: str) -> None:
    AdapterCapabilities(code=code, name=code, auth_kind="api_key")  # no raise


@pytest.mark.unit
@pytest.mark.parametrize("code", ["", "with space", "with.dot", "with/slash", "with!bang"])
def test_capabilities_rejects_invalid_code(code: str) -> None:
    with pytest.raises(ValueError, match="code"):
        AdapterCapabilities(code=code, name="X", auth_kind="api_key")


@pytest.mark.unit
@pytest.mark.parametrize("field", ["rate_limit_rps", "rate_limit_burst"])
def test_capabilities_rejects_zero_or_negative_rate(field: str) -> None:
    with pytest.raises(ValueError):
        AdapterCapabilities(code="x", name="X", auth_kind="api_key", **{field: 0})
    with pytest.raises(ValueError):
        AdapterCapabilities(code="x", name="X", auth_kind="api_key", **{field: -1})


@pytest.mark.unit
def test_capabilities_round_trip_tags() -> None:
    caps = AdapterCapabilities(
        code="x",
        name="X",
        auth_kind="api_key",
        tags=frozenset({"marketplace", "az"}),
    )
    assert "marketplace" in caps.tags
    assert "az" in caps.tags
