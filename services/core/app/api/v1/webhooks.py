"""Channel webhook ingress (AI-2.5.4, roadmap §17.3 inbound).

``POST /v1/channels/{tenant_id}/{code}/webhook`` is the door every channel
posts orders through. The flow:

1. Look up the channel by ``(tenant_id, code)`` via the system pool (no
   user-tenant context to apply — the request isn't authenticated as a user).
2. Read the per-channel webhook secret from ``channel.config``.
3. Verify the HMAC signature in the channel-specific header (declared in the
   adapter's :class:`AdapterCapabilities.webhook_signature_header`).
4. Hand the raw body to ``adapter.normalize_webhook`` for canonical parsing.
5. Insert into ``channel_orders`` with the channel's
   ``UNIQUE(channel_id, channel_order_id)`` constraint — a redelivered
   webhook trips it and returns ``200`` without a second insert
   (at-least-once → exactly-once).
6. Return ``200 OK`` with the canonical order's ``channel_order_id`` so the
   channel's retry loop stops.

The endpoint NEVER touches the per-request RLS pool: it's not a user-driven
endpoint, so there's no Bearer token / Keycloak subject to resolve. The
system (owner) pool bypasses RLS — the WITH CHECK still passes because the
insert carries the correct ``tenant_id``.

Reservation / fulfillment is AI-2.5.5 — this endpoint only persists the
canonical order.
"""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from libs.adapter import AdapterPermanentError, verify_signature

from ...infrastructure.db.models import Channel, ChannelOrder

router = APIRouter(tags=["webhooks"])


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

        secret = channel.config.get("webhook_secret") if isinstance(channel.config, dict) else None
        if not secret:
            raise HTTPException(status_code=503, detail="channel has no webhook secret configured")
        signature_header = adapter.capabilities.webhook_signature_header
        if signature_header is None:
            raise HTTPException(
                status_code=503, detail="adapter declares no webhook signature header"
            )
        signature = request.headers.get(signature_header)
        if not verify_signature(body=body, secret=str(secret), signature=signature):
            raise HTTPException(status_code=401, detail="invalid webhook signature")

        try:
            canonical = adapter.normalize_webhook(body=body, headers=dict(request.headers))
        except AdapterPermanentError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc

        # Use a savepoint so a redelivered webhook (UNIQUE violation) rolls back
        # only the duplicate insert; the outer transaction still commits cleanly
        # with no side effects.
        duplicate = False
        try:
            async with session.begin_nested():
                session.add(
                    ChannelOrder(
                        tenant_id=tenant_id,
                        channel_id=channel.id,
                        channel_order_id=canonical.channel_order_id,
                        canonical_payload=orjson.loads(canonical.model_dump_json()),
                        status="received",
                    )
                )
        except IntegrityError:
            duplicate = True

    return {
        "channel_order_id": canonical.channel_order_id,
        "status": "duplicate" if duplicate else "received",
    }
