"""AI-1.17 — feature flag registry + override resolution (unit, no IO)."""

from __future__ import annotations

import pytest

from libs.feature_flags import FlagRegistry, FlagSpec, UnknownFlagError

_SPECS = [
    FlagSpec("alpha", default=False, description="Alpha"),
    FlagSpec("beta", default=True, description="Beta"),
]


@pytest.fixture
def registry() -> FlagRegistry:
    return FlagRegistry(_SPECS)


@pytest.mark.unit
def test_keys_and_specs_preserve_order(registry: FlagRegistry) -> None:
    assert registry.keys() == ("alpha", "beta")
    assert [spec.key for spec in registry.specs()] == ["alpha", "beta"]


@pytest.mark.unit
def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        FlagRegistry([FlagSpec("x", default=True, description="a"), FlagSpec("x", False, "b")])


@pytest.mark.unit
def test_contains(registry: FlagRegistry) -> None:
    assert "alpha" in registry
    assert "missing" not in registry


@pytest.mark.unit
def test_require_known_passes(registry: FlagRegistry) -> None:
    registry.require("alpha")  # no raise


@pytest.mark.unit
def test_require_unknown_raises(registry: FlagRegistry) -> None:
    with pytest.raises(UnknownFlagError) as exc:
        registry.require("missing")
    assert exc.value.key == "missing"


@pytest.mark.unit
def test_defaults(registry: FlagRegistry) -> None:
    assert registry.defaults() == {"alpha": False, "beta": True}


@pytest.mark.unit
def test_resolve_overlays_overrides(registry: FlagRegistry) -> None:
    assert registry.resolve({"alpha": True}) == {"alpha": True, "beta": True}


@pytest.mark.unit
def test_resolve_ignores_unknown_overrides(registry: FlagRegistry) -> None:
    # A stale DB row for a removed flag must not leak into the effective set.
    assert registry.resolve({"removed": True}) == {"alpha": False, "beta": True}


@pytest.mark.unit
def test_resolve_does_not_mutate_defaults(registry: FlagRegistry) -> None:
    registry.resolve({"alpha": True})
    assert registry.defaults() == {"alpha": False, "beta": True}
