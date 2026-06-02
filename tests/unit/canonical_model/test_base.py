"""AI-1.4 — canonical base invariants: v1, frozen, strict, version not serialized."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.canonical_model import CanonicalInventory, CanonicalProduct


@pytest.mark.unit
def test_schema_version_is_v1() -> None:
    assert CanonicalProduct.schema_version == "v1"
    assert CanonicalInventory.schema_version == "v1"


@pytest.mark.unit
def test_models_are_frozen() -> None:
    inv = CanonicalInventory(sku="S", qty=5)
    with pytest.raises(ValidationError):
        inv.qty = 10  # type: ignore[misc]


@pytest.mark.unit
def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalInventory(sku="S", qty=5, bogus=1)  # type: ignore[call-arg]


@pytest.mark.unit
def test_schema_version_is_not_serialized() -> None:
    # ClassVar marks the version without bloating every payload.
    assert "schema_version" not in CanonicalInventory(sku="S", qty=5).model_dump()
