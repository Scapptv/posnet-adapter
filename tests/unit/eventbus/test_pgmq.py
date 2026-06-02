"""AI-1.14 — jsonb coercion contract (psycopg3 gives dicts; text is a fallback)."""

from __future__ import annotations

import pytest

from libs.eventbus.pgmq import _as_dict


@pytest.mark.unit
def test_as_dict_passes_through_a_dict() -> None:
    assert _as_dict({"a": 1}) == {"a": 1}


@pytest.mark.unit
def test_as_dict_parses_json_text() -> None:
    assert _as_dict('{"a": 1}') == {"a": 1}
