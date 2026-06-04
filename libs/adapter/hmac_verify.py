"""Constant-time HMAC verification for inbound webhooks (AI-2.5.4).

Every channel webhook header carries some form of HMAC over the raw body —
``sha256=<hex>`` (Stripe-style, what we accept here) or the bare hex digest.
The endpoint computes the same MAC with the channel's secret and compares;
``hmac.compare_digest`` keeps the comparison constant-time so a chunked
forge attempt can't read timing through the verify path.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(*, body: bytes, secret: str, signature: str | None) -> bool:
    """Return ``True`` iff ``signature`` is a valid HMAC-SHA256 of ``body``
    under ``secret``.

    Accepted signature shapes:

    * ``"sha256=<hex>"`` (Stripe / GitHub convention)
    * bare ``"<hex>"`` (lowercase) — for channels that don't prefix

    Anything else is rejected. Missing signature returns ``False``.
    """
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    candidate = signature.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, candidate)
