"""Unit tests for the ULID-format Idempotency-Key generator."""

from __future__ import annotations

import re
import time

import pytest

from libs.loyalty_client.idempotency import new_idempotency_key

# Crockford base32 alphabet — same set Paylo's middleware will accept.
_PAYLO_ACCEPTS = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
_CROCKFORD = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


@pytest.mark.unit
def test_format_matches_paylo_validator() -> None:
    """Every generated key must be acceptable to Paylo's middleware regex."""
    key = new_idempotency_key()
    assert _PAYLO_ACCEPTS.match(key), key


@pytest.mark.unit
def test_format_is_crockford_ulid_shape() -> None:
    """26 chars, only Crockford alphabet — sortable, URL-safe, no ambiguous chars."""
    key = new_idempotency_key()
    assert _CROCKFORD.match(key), key


@pytest.mark.unit
def test_uniqueness_across_batch() -> None:
    """No collisions across 10k keys generated in the same process — the 80-bit
    random tail makes collisions astronomically unlikely."""
    keys = {new_idempotency_key() for _ in range(10_000)}
    assert len(keys) == 10_000


@pytest.mark.unit
def test_keys_sort_in_creation_order() -> None:
    """ULIDs are designed to sort lexicographically. The 10-char ms timestamp
    prefix guarantees ordering across ms boundaries."""
    first = new_idempotency_key()
    time.sleep(0.002)
    second = new_idempotency_key()
    time.sleep(0.002)
    third = new_idempotency_key()
    assert first < second < third
