"""Unit tests for the HMAC verify helper (AI-2.5.4)."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from libs.adapter import verify_signature

_SECRET = "channel-secret-2026"  # pragma: allowlist secret


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.unit
def test_valid_signature_with_sha256_prefix() -> None:
    body = b'{"order": 1}'
    assert verify_signature(body=body, secret=_SECRET, signature=_sign(body)) is True


@pytest.mark.unit
def test_valid_signature_without_prefix() -> None:
    """Bare hex digest (some channels don't use the ``sha256=`` prefix)."""
    body = b'{"x": 1}'
    digest = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body=body, secret=_SECRET, signature=digest) is True


@pytest.mark.unit
def test_uppercase_signature_is_normalised() -> None:
    body = b"abc"
    digest = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body=body, secret=_SECRET, signature=digest.upper()) is True


@pytest.mark.unit
def test_wrong_secret_rejects() -> None:
    body = b'{"order": 1}'
    other_secret = "different"  # pragma: allowlist secret
    assert verify_signature(body=body, secret=other_secret, signature=_sign(body)) is False


@pytest.mark.unit
def test_tampered_body_rejects() -> None:
    signed = _sign(b'{"order": 1}')
    assert verify_signature(body=b'{"order": 2}', secret=_SECRET, signature=signed) is False


@pytest.mark.unit
def test_missing_signature_rejects() -> None:
    assert verify_signature(body=b"x", secret=_SECRET, signature=None) is False
    assert verify_signature(body=b"x", secret=_SECRET, signature="") is False


@pytest.mark.unit
def test_garbage_signature_rejects() -> None:
    assert verify_signature(body=b"x", secret=_SECRET, signature="not-a-hex") is False
    assert verify_signature(body=b"x", secret=_SECRET, signature="sha256=") is False
