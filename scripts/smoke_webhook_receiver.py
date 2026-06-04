"""Tiny HTTP server that accepts a Paylo webhook, verifies it via WebhookVerifier
and prints the typed event. Used for end-to-end smoke.

Run::

    PAYLO_WEBHOOK_SECRET=<the secret from pos:register-webhook> \
        .venv/Scripts/python.exe scripts/smoke_webhook_receiver.py

Then on the Paylo side trigger a reverse — this receiver prints the event."""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from libs.loyalty_client import (
    AdminReverseEvent,
    BucketExpireEvent,
    WebhookEventError,
    WebhookVerificationError,
    WebhookVerifier,
)

SECRET = os.environ.get("PAYLO_WEBHOOK_SECRET")
if not SECRET:
    sys.stderr.write("PAYLO_WEBHOOK_SECRET env required\n")
    raise SystemExit(2)

VERIFIER = WebhookVerifier(SECRET)
PORT = int(os.environ.get("PORT", "9876"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        try:
            event = VERIFIER.verify_and_parse(
                body=body,
                timestamp=self.headers.get("X-Paylo-Timestamp", ""),
                signature=self.headers.get("X-Paylo-Signature", ""),
                event_type=self.headers.get("X-Paylo-Event", ""),
            )
        except WebhookVerificationError as exc:
            sys.stdout.write(f"REJECTED (auth): {exc}\n")
            self.send_response(401)
            self.end_headers()
            return
        except WebhookEventError as exc:
            sys.stdout.write(f"REJECTED (event): {exc}\n")
            self.send_response(400)
            self.end_headers()
            return

        event_id = self.headers.get("X-Paylo-Event-Id", "?")
        if isinstance(event, AdminReverseEvent):
            sys.stdout.write(
                f"OK admin_reverse event_id={event_id} tx={event.transaction_id} "
                f"receipt={event.receipt_no} reason={event.reason!r}\n"
            )
        elif isinstance(event, BucketExpireEvent):
            sys.stdout.write(
                f"OK bucket_expire event_id={event_id} bucket={event.bucket_id} "
                f"customer={event.customer_id} expired={event.amount_expired_cents}\n"
            )
        sys.stdout.flush()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format: str, *args: object) -> None:
        return  # quiet


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    sys.stdout.write(f"listening on http://127.0.0.1:{PORT}\n")
    sys.stdout.flush()
    server.serve_forever()
