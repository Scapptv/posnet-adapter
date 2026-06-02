"""AI-1.9.2 — request-id logging processor."""

from __future__ import annotations

import pytest

from services.core.app.logging_config import add_request_id, configure_logging
from services.core.app.middleware.request_id import request_id_ctx


@pytest.mark.unit
def test_add_request_id_injects_when_set() -> None:
    token = request_id_ctx.set("rid-9")
    try:
        event = add_request_id(None, "info", {"event": "x"})
    finally:
        request_id_ctx.reset(token)
    assert event["request_id"] == "rid-9"


@pytest.mark.unit
def test_add_request_id_noop_when_unset() -> None:
    assert "request_id" not in add_request_id(None, "info", {"event": "x"})


@pytest.mark.unit
def test_configure_logging_both_renderers() -> None:
    # Exercise the JSON branch, then restore console config for other tests.
    try:
        configure_logging(json_logs=True)
    finally:
        configure_logging(json_logs=False)
