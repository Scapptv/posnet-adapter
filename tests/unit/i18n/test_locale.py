"""AI-1.17 — Accept-Language parsing + locale negotiation (unit, no IO)."""

from __future__ import annotations

import pytest

from libs.i18n import negotiate_locale, parse_accept_language

_SUPPORTED = ("az", "en", "tr", "ru")


# ---- parse_accept_language ----


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("az", ["az"]),
        ("az-AZ", ["az-az"]),  # lower-cased
        ("az-AZ,az;q=0.9,en;q=0.8", ["az-az", "az", "en"]),
        ("en;q=0.5,az;q=0.9", ["az", "en"]),  # reordered by q
        ("en,az", ["en", "az"]),  # equal q keeps header order
        ("*;q=1.0,az", ["az"]),  # wildcard dropped
        ("en;q=0", []),  # q=0 dropped
        ("en;q=abc", []),  # malformed q -> dropped
        ("tr ; q=0.7 , ru", ["ru", "tr"]),  # whitespace tolerated
    ],
)
def test_parse_accept_language(header: str | None, expected: list[str]) -> None:
    assert parse_accept_language(header) == expected


# ---- negotiate_locale ----


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "az"),  # no header -> default
        ("", "az"),
        ("az-AZ,en;q=0.8", "az"),  # exact primary subtag
        ("en-US", "en"),  # regional -> primary fallback
        ("EN", "en"),  # case-insensitive
        ("ru,tr;q=0.9", "ru"),  # highest q wins
        ("fr", "az"),  # unsupported -> default
        ("fr-FR,tr;q=0.5", "tr"),  # skips unsupported, takes next
    ],
)
def test_negotiate_locale(header: str | None, expected: str) -> None:
    assert negotiate_locale(header, _SUPPORTED, "az") == expected
