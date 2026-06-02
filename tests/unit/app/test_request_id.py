"""AI-1.9.2 — request-id middleware: generate, echo, surface in body."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_request_id_generated_when_absent(test_app: FastAPI) -> None:
    with TestClient(test_app) as client:
        response = client.get("/raise/domain")
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert len(request_id) >= 8


@pytest.mark.unit
def test_request_id_echoed_when_provided(test_app: FastAPI) -> None:
    with TestClient(test_app) as client:
        response = client.get("/raise/domain", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    # and it flows into the problem body
    assert response.json()["request_id"] == "abc-123"
