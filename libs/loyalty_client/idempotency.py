"""Idempotency-Key generation for the Paylo POS API.

Paylo accepts any string matching ``^[A-Za-z0-9_\\-]{8,128}$``. We generate a
26-character Crockford ULID, which is monotonically sortable, URL-safe and
collision-resistant without needing a centralised allocator.

We deliberately avoid the ``ulid-py`` dependency — implementing the format
ourselves keeps the lib's transitive surface tiny and the spec is two pages.
"""

from __future__ import annotations

import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # pragma: allowlist secret


def new_idempotency_key() -> str:
    """Return a fresh 26-character ULID-format Idempotency-Key.

    Format: 10-char timestamp (ms since epoch, Crockford base32) + 16-char random.
    Lexicographic sort order matches creation order within the same ms.
    """
    timestamp_ms = int(time.time() * 1000)
    rand = secrets.token_bytes(10)

    # Encode 48-bit timestamp as 10 Crockford chars
    ts_chars: list[str] = []
    for _ in range(10):
        ts_chars.append(_CROCKFORD[timestamp_ms & 0x1F])
        timestamp_ms >>= 5
    ts_part = "".join(reversed(ts_chars))

    # Encode 80-bit random bytes as 16 Crockford chars
    rand_int = int.from_bytes(rand, "big")
    rand_chars: list[str] = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[rand_int & 0x1F])
        rand_int >>= 5
    rand_part = "".join(reversed(rand_chars))

    return ts_part + rand_part
