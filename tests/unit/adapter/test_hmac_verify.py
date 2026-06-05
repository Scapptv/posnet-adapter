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


# ----------------------------------------------------------------
# H1 (ADR-0020) — timestamp-bound replay protection
# ----------------------------------------------------------------


def _sign_ts(body: bytes, ts: int, secret: str = _SECRET) -> str:
    """Sign the timestamp-bound payload the verifier reconstructs: ``"{ts}." + body``."""
    signed = f"{ts}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


@pytest.mark.unit
def test_timestamped_signature_within_window_passes() -> None:
    body = b'{"order": 1}'
    now = 1_000_000.0
    ts = int(now)
    assert (
        verify_signature(
            body=body, secret=_SECRET, signature=_sign_ts(body, ts), timestamp=str(ts), now=now
        )
        is True
    )


@pytest.mark.unit
def test_stale_timestamp_is_rejected_even_with_valid_mac() -> None:
    """A captured delivery replayed after the window closes must fail."""
    body = b'{"order": 1}'
    now = 1_000_000.0
    ts = int(now) - 301  # just outside the default 300s window
    assert (
        verify_signature(
            body=body, secret=_SECRET, signature=_sign_ts(body, ts), timestamp=str(ts), now=now
        )
        is False
    )


@pytest.mark.unit
def test_future_timestamp_is_rejected() -> None:
    body = b"x"
    now = 1_000_000.0
    ts = int(now) + 301
    assert (
        verify_signature(
            body=body, secret=_SECRET, signature=_sign_ts(body, ts), timestamp=str(ts), now=now
        )
        is False
    )


@pytest.mark.unit
def test_malformed_timestamp_is_rejected() -> None:
    body = b"x"
    assert (
        verify_signature(
            body=body,
            secret=_SECRET,
            signature=_sign_ts(body, 1_000_000),
            timestamp="not-int",
            now=1_000_000.0,
        )
        is False
    )


@pytest.mark.unit
def test_timestamp_is_bound_into_mac() -> None:
    """A MAC signed for ts1 must not verify when presented with ts2 (the
    attacker can't slide the timestamp forward to refresh the window)."""
    body = b"x"
    now = 1_000_000.0
    sig_for_old = _sign_ts(body, int(now) - 10)
    # Present a fresh (in-window) timestamp with the old MAC → mismatch.
    assert (
        verify_signature(
            body=body, secret=_SECRET, signature=sig_for_old, timestamp=str(int(now)), now=now
        )
        is False
    )


@pytest.mark.unit
def test_body_only_signing_still_works_without_timestamp() -> None:
    """Backward compat: no timestamp → legacy body-only HMAC (unchanged)."""
    body = b'{"legacy": true}'
    assert verify_signature(body=body, secret=_SECRET, signature=_sign(body)) is True
