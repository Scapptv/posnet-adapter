"""Unit tests for request-id helpers."""

from __future__ import annotations

from uuid import UUID

from libs.common.request_id import REQUEST_ID_HEADER, generate_request_id


def test_generate_is_uuid() -> None:
    UUID(generate_request_id())  # raises if not a valid UUID


def test_generate_is_unique() -> None:
    assert generate_request_id() != generate_request_id()


def test_header_constant() -> None:
    assert REQUEST_ID_HEADER == "X-Request-ID"
