"""Unit tests for the inbound webhook verifier on the Posnet side."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from libs.loyalty_client import (
    AdminReverseEvent,
    BucketExpireEvent,
    WebhookEventError,
    WebhookVerificationError,
    WebhookVerifier,
)

SECRET = "deadbeefdeadbeefdeadbeefdeadbeef" * 2  # 64 hex chars  # pragma: allowlist secret


def _sign(body: bytes, ts: int) -> str:
    payload = str(ts).encode() + b"." + body
    return "sha256=" + hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _admin_reverse_payload(event_id: str = "01HX7K3R4M5N6P7Q8R9SABCDEF") -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "admin_reverse",
        "occurred_at": "2026-06-04T13:00:00+04:00",
        "data": {
            "transaction_id": 147,
            "receipt_no": "R-001",
            "merchant_id": 1,
            "customer_id": 8,
            "return_receipt_no": "RET-001",
            "reason": "customer dispute",
            "reversed_at": "2026-06-04T13:00:00+04:00",
            "actor_id": 1,
            "source": "admin.transaction.reverse",
        },
    }


def _bucket_expire_payload(event_id: str = "01HX7K3R4M5N6P7Q8R9SBUCKET") -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "bucket_expire",
        "occurred_at": "2026-06-04T03:00:00+04:00",
        "data": {
            "bucket_id": 42,
            "merchant_id": 1,
            "customer_id": 8,
            "amount_expired_cents": 250,
            "new_balance": 0,
            "threshold": "2026-06-04T03:00:00+04:00",
            "expired_at": "2026-06-04T03:00:00+04:00",
        },
    }


@pytest.mark.unit
def test_verify_passes_for_valid_signature() -> None:
    v = WebhookVerifier(SECRET)
    body = json.dumps(_admin_reverse_payload(), separators=(",", ":")).encode()
    ts = int(time.time())
    v.verify(body=body, timestamp=str(ts), signature=_sign(body, ts))  # no exception


@pytest.mark.unit
def test_verify_rejects_constructed_with_empty_secret() -> None:
    with pytest.raises(ValueError):
        WebhookVerifier("")


@pytest.mark.unit
def test_verify_rejects_tampered_body() -> None:
    v = WebhookVerifier(SECRET)
    body = json.dumps(_admin_reverse_payload(), separators=(",", ":")).encode()
    ts = int(time.time())
    sig = _sign(body, ts)

    tampered = body.replace(b'"actor_id":1', b'"actor_id":999')
    with pytest.raises(WebhookVerificationError, match="signature mismatch"):
        v.verify(body=tampered, timestamp=str(ts), signature=sig)


@pytest.mark.unit
def test_verify_rejects_expired_timestamp() -> None:
    v = WebhookVerifier(SECRET)
    body = b"{}"
    stale_ts = int(time.time()) - 400  # outside ±300s window
    with pytest.raises(WebhookVerificationError, match="replay window"):
        v.verify(body=body, timestamp=str(stale_ts), signature=_sign(body, stale_ts))


@pytest.mark.unit
def test_verify_rejects_future_timestamp() -> None:
    v = WebhookVerifier(SECRET)
    body = b"{}"
    future_ts = int(time.time()) + 400
    with pytest.raises(WebhookVerificationError, match="replay window"):
        v.verify(body=body, timestamp=str(future_ts), signature=_sign(body, future_ts))


@pytest.mark.unit
def test_verify_rejects_malformed_timestamp() -> None:
    v = WebhookVerifier(SECRET)
    body = b"{}"
    with pytest.raises(WebhookVerificationError, match="malformed timestamp"):
        v.verify(body=body, timestamp="not-an-int", signature="sha256=" + "a" * 64)


@pytest.mark.unit
def test_verify_rejects_signature_without_prefix() -> None:
    v = WebhookVerifier(SECRET)
    body = b"{}"
    ts = int(time.time())
    with pytest.raises(WebhookVerificationError, match="sha256="):
        v.verify(body=body, timestamp=str(ts), signature="abc123")


@pytest.mark.unit
def test_verify_and_parse_decodes_admin_reverse_event() -> None:
    v = WebhookVerifier(SECRET)
    raw = _admin_reverse_payload()
    body = json.dumps(raw, separators=(",", ":")).encode()
    ts = int(time.time())

    event = v.verify_and_parse(
        body=body,
        timestamp=str(ts),
        signature=_sign(body, ts),
        event_type="admin_reverse",
    )

    assert isinstance(event, AdminReverseEvent)
    assert event.transaction_id == 147
    assert event.receipt_no == "R-001"
    assert event.merchant_id == 1
    assert event.reason == "customer dispute"


@pytest.mark.unit
def test_verify_and_parse_decodes_bucket_expire_event() -> None:
    v = WebhookVerifier(SECRET)
    raw = _bucket_expire_payload()
    body = json.dumps(raw, separators=(",", ":")).encode()
    ts = int(time.time())

    event = v.verify_and_parse(
        body=body,
        timestamp=str(ts),
        signature=_sign(body, ts),
        event_type="bucket_expire",
    )

    assert isinstance(event, BucketExpireEvent)
    assert event.bucket_id == 42
    assert event.amount_expired_cents == 250
    assert event.new_balance == 0


@pytest.mark.unit
def test_verify_and_parse_rejects_event_type_mismatch_between_header_and_body() -> None:
    """Defense: a signed body claims one event_type, but the X-Paylo-Event
    header says another. This shouldn't happen in practice — surfaces a Paylo
    bug or a tampering attempt that didn't quite mutate the right bytes."""
    v = WebhookVerifier(SECRET)
    raw = _admin_reverse_payload()
    body = json.dumps(raw, separators=(",", ":")).encode()
    ts = int(time.time())

    with pytest.raises(WebhookEventError, match="does not match"):
        v.verify_and_parse(
            body=body,
            timestamp=str(ts),
            signature=_sign(body, ts),
            event_type="bucket_expire",  # WRONG — body is admin_reverse
        )


@pytest.mark.unit
def test_verify_and_parse_rejects_unknown_event_type() -> None:
    """Future-proofing: if Paylo rolls out a new event_type we haven't modelled
    yet, we should fail loudly so the receiver returns 400. Silently dropping
    would lose audit-relevant data."""
    v = WebhookVerifier(SECRET)
    raw = {
        "event_id": "01HX",
        "event_type": "new_event_in_paylo_we_dont_know_yet",
        "occurred_at": "2026-06-04T13:00:00+04:00",
        "data": {},
    }
    body = json.dumps(raw, separators=(",", ":")).encode()
    ts = int(time.time())

    with pytest.raises(WebhookEventError, match="unknown event_type"):
        v.verify_and_parse(
            body=body,
            timestamp=str(ts),
            signature=_sign(body, ts),
            event_type="new_event_in_paylo_we_dont_know_yet",
        )


@pytest.mark.unit
def test_verify_and_parse_rejects_non_json_body() -> None:
    v = WebhookVerifier(SECRET)
    body = b"not json"
    ts = int(time.time())
    with pytest.raises(WebhookEventError, match="not valid JSON"):
        v.verify_and_parse(
            body=body, timestamp=str(ts), signature=_sign(body, ts), event_type="admin_reverse"
        )
