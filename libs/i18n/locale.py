"""Locale negotiation from the HTTP ``Accept-Language`` header (AI-1.17).

``parse_accept_language`` turns the header into the client's languages ordered by
quality, and ``negotiate_locale`` matches them against the locales we actually
serve (delegating the match to Babel), falling back to a default. Pure functions —
no request/IO coupling, so the FastAPI dependency stays a thin wrapper.
"""

from __future__ import annotations

from collections.abc import Sequence

from babel import negotiate_locale as _babel_negotiate


def parse_accept_language(header: str | None) -> list[str]:
    """Return the header's language tags, lower-cased and ordered by ``q`` (desc).

    Wildcards and ``q=0`` (explicitly-refused) tags are dropped; tags of equal
    quality keep their header order. A missing/blank header yields ``[]``.
    """
    if not header:
        return []

    ranked: list[tuple[float, int, str]] = []
    for position, raw in enumerate(header.split(",")):
        tag, _, params = raw.strip().partition(";")
        tag = tag.strip().lower()
        if not tag or tag == "*":
            continue
        quality = _quality(params)
        if quality <= 0:
            continue
        ranked.append((quality, position, tag))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [tag for _quality, _position, tag in ranked]


def _quality(params: str) -> float:
    params = params.strip().lower()
    if not params.startswith("q="):
        return 1.0
    try:
        return float(params[2:].split(";")[0])
    except ValueError:
        return 0.0


def negotiate_locale(accept_language: str | None, supported: Sequence[str], default: str) -> str:
    """Pick the best of ``supported`` for the client, or ``default`` if none match."""
    match = _babel_negotiate(parse_accept_language(accept_language), list(supported), sep="-")
    if match is not None and match in supported:
        return match
    return default
