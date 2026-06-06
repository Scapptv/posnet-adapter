"""Channel webhook ingress (AI-2.5.4 + AI-2.5.5, roadmap §17.3 inbound).

``POST /v1/channels/{tenant_id}/{code}/webhook`` is the door every channel
posts orders through. The flow:

1. Look up the channel by ``(tenant_id, code)`` via the system pool (no
   user-tenant context to apply — the request isn't authenticated as a user).
2. Read the per-channel webhook secret from ``channel.config``.
3. Verify the HMAC signature in the channel-specific header (declared in the
   adapter's :class:`AdapterCapabilities.webhook_signature_header`).
4. Hand the raw body to ``adapter.normalize_webhook`` for canonical parsing.
5. ``ingest_channel_order`` (AI-2.5.5): insert into ``channel_orders``
   (``UNIQUE(channel_id, channel_order_id)`` makes redelivery idempotent) and
   **reserve POS stock** for every line — anti-oversell, all-or-nothing. The
   order ends ``reserved`` (stock held) or ``rejected`` (unknown SKU / oversold)
   but is always persisted.
6. After the transaction commits, **acknowledge** the outcome back to the
   channel (best-effort — a failed ack never fails the webhook; reconciliation
   AI-2.5.6 retries the miss).
7. Return ``200 OK`` with the canonical ``channel_order_id`` + final status so
   the channel's retry loop stops.

The endpoint NEVER touches the per-request RLS pool: it's not a user-driven
endpoint, so there's no Bearer token / Keycloak subject to resolve. The
system (owner) pool bypasses RLS — the WITH CHECK still passes because every
insert carries the correct ``tenant_id``.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import AdapterError, AdapterPermanentError, verify_signature
from libs.canonical_model import CanonicalOrder

from ...infrastructure.db.models import Channel
from ...sync.channel_config import parse_channel_config
from ...sync.observability import sync_span
from ...sync.order_ingest import ingest_channel_order

_log = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


async def _write_order_to_pos(
    request: Request, *, tenant_id: UUID, order: CanonicalOrder, channel_code: str
) -> None:
    """Best-effort: write a reserved channel order back into the POS (Posnet),
    the source of truth (AI-2.8.3, §17.7 — the tail of the inbound flow).

    The reservation is already durable; a POS hiccup must not undo it, so a
    failure is logged and left for reconciliation/retry — exactly like a failed
    channel ack. Skipped when no POS is wired (``pos_source_factory`` unset, or
    the tenant has no connector) or the POS is read-only.
    """
    factory = getattr(request.app.state, "pos_source_factory", None)
    if factory is None:
        return
    pos_source = factory(tenant_id)
    if pos_source is None or not pos_source.capabilities.supports_push_order:
        return
    try:
        with sync_span("pos.push_order", channel_code=channel_code):
            await pos_source.push_order(order)
    except (AdapterError, NotImplementedError) as exc:
        _log.warning(
            "pos_write_back_failed",
            extra={
                "tenant_id": str(tenant_id),
                "channel_code": channel_code,
                "channel_order_id": order.channel_order_id,
                "error_type": type(exc).__name__,
            },
        )


@router.post(
    "/channels/{tenant_id}/{code}/webhook",
    status_code=status.HTTP_200_OK,
)
async def receive_webhook(
    tenant_id: UUID,
    code: str,
    request: Request,
) -> dict[str, str]:
    """Land one webhook delivery for ``(tenant_id, code)``."""
    factory = getattr(request.app.state, "webhook_adapter_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="webhook ingress is not wired")

    system_sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.system_sessionmaker
    body = await request.body()

    async with system_sessionmaker() as session, session.begin():
        channel = (
            await session.execute(
                select(Channel).where(Channel.tenant_id == tenant_id, Channel.code == code)
            )
        ).scalar_one_or_none()
        if channel is None or channel.status != "active":
            raise HTTPException(status_code=404, detail="channel not found or inactive")

        adapter = factory(channel)
        if not adapter.capabilities.supports_webhook_orders:
            raise HTTPException(
                status_code=400, detail="channel adapter does not support webhook orders"
            )

        secret = parse_channel_config(channel.config).webhook_secret
        if not secret:
            raise HTTPException(status_code=503, detail="channel has no webhook secret configured")
        signature_header = adapter.capabilities.webhook_signature_header
        if signature_header is None:
            raise HTTPException(
                status_code=503, detail="adapter declares no webhook signature header"
            )
        signature = request.headers.get(signature_header)
        # Replay protection (H1, ADR-0020): if the adapter declares a timestamp
        # header, bind it into the HMAC and reject deliveries outside the skew
        # window. Channels that don't sign a timestamp fall back to body-only.
        timestamp_header = adapter.capabilities.webhook_timestamp_header
        timestamp = request.headers.get(timestamp_header) if timestamp_header else None
        if timestamp_header is not None and not timestamp:
            raise HTTPException(status_code=401, detail="missing webhook timestamp")
        if not verify_signature(
            body=body, secret=str(secret), signature=signature, timestamp=timestamp
        ):
            raise HTTPException(status_code=401, detail="invalid webhook signature")

        try:
            canonical = adapter.normalize_webhook(body=body, headers=dict(request.headers))
        except AdapterPermanentError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc

        with sync_span("channel.ingest", channel_code=code) as span:
            outcome = await ingest_channel_order(
                session, tenant_id=tenant_id, channel_id=channel.id, order=canonical
            )
            span.set_attribute("status", outcome.status)

    # Transaction committed: the order (and any reservations) are durable.
    # AI-2.8.3 (§17.7): record a reserved order back into the POS (Posnet) — the
    # source of truth — so its stock/sales reflect the marketplace sale. Like
    # the ack below: best-effort + post-commit, reconciled on failure.
    if outcome.status == "reserved":
        await _write_order_to_pos(request, tenant_id=tenant_id, order=canonical, channel_code=code)

    # Now tell the channel — best-effort, so a channel-side hiccup can't undo a
    # safely-persisted order. Reconciliation (AI-2.5.6) sweeps up missed acks.
    if outcome.ack_status is not None:
        try:
            await adapter.acknowledge_order(
                channel_order_id=outcome.channel_order_id, status=outcome.ack_status
            )
        except AdapterError as exc:
            _log.warning(
                "webhook_ack_failed",
                extra={
                    "channel_id": str(channel.id),
                    "channel_code": code,
                    "channel_order_id": outcome.channel_order_id,
                    "error_type": type(exc).__name__,
                    "error_message": exc.message,
                },
            )

    return {"channel_order_id": outcome.channel_order_id, "status": outcome.status}
