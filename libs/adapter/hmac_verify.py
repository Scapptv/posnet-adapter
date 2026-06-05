"""Constant-time HMAC verification for inbound webhooks (AI-2.5.4 + H1).

Every channel webhook header carries some form of HMAC over the raw body —
``sha256=<hex>`` (Stripe-style, what we accept here) or the bare hex digest.
The endpoint computes the same MAC with the channel's secret and compares;
``hmac.compare_digest`` keeps the comparison constant-time so a chunked forge
attempt can't read timing through the verify path.

Replay protection (H1, ADR-0020): when the channel also signs a timestamp the
MAC binds it (``"{ts}." + body``) and the verifier rejects deliveries outside a
skew window — a captured-and-replayed delivery stops passing once the window
closes. This mirrors the loyalty webhook verifier so both ingress paths share
one hardened convention.
"""

from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_MAX_SKEW_SECONDS = 300
"""A delivery whose signed timestamp is more than this far from now (clock skew
+ network) is rejected even with a valid HMAC. ±300s matches the loyalty path."""


def verify_signature(
    *,
    body: bytes,
    secret: str,
    signature: str | None,
    timestamp: str | None = None,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
    now: float | None = None,
) -> bool:
    """Return ``True`` iff ``signature`` is a valid HMAC-SHA256 for ``body``
    under ``secret``.

    Accepted signature shapes:

    * ``"sha256=<hex>"`` (Stripe / GitHub convention)
    * bare ``"<hex>"`` (lowercase) — for channels that don't prefix

    Anything else is rejected. Missing signature returns ``False``.

    Replay protection (H1, ADR-0020): when ``timestamp`` is supplied the signed
    payload is ``f"{ts}.".encode() + body`` (so the MAC binds the time) and the
    timestamp must be within ``max_skew_seconds`` of ``now`` (defaults to wall
    clock ``time.time()``). A non-integer timestamp is rejected. Without a
    timestamp it falls back to body-only HMAC (legacy; no replay protection —
    only for channels that don't sign a time).
    """
    if not signature:
        return False
    if timestamp is not None:
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        current = time.time() if now is None else now
        if abs(current - ts) > max_skew_seconds:
            return False
        signed = f"{ts}.".encode() + body
    else:
        signed = body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    candidate = signature.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, candidate)
