"""Async Paylo loyalty API client.

The client is a thin wrapper around :class:`httpx.AsyncClient` that:
  * Injects ``Authorization: Bearer <token>`` and ``Accept: application/json``.
  * Auto-generates an ``Idempotency-Key`` on every state-changing call unless
    the caller supplies one explicitly (e.g. when retrying after losing the
    response of an earlier attempt).
  * Maps Paylo's typed error responses to the :mod:`.errors` hierarchy so the
    caller can ``except`` on the specific failure mode.
  * Retries transient failures (5xx, network, 429) with exponential backoff
    via :mod:`tenacity`, and trips a :mod:`pybreaker` circuit breaker if
    Paylo stays down so we fail fast instead of piling timeouts.
  * Emits structured logs via :mod:`structlog` so each call carries the
    transaction's ``receipt_no`` / ``idempotency_key`` / ``status_code``.

The client owns the underlying ``httpx.AsyncClient`` lifecycle when used as an
async context manager. For longer-lived service use, pass an existing client.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Self

import httpx
import pybreaker
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .errors import (
    LoyaltyAbilityError,
    LoyaltyAuthError,
    LoyaltyError,
    LoyaltyIdempotencyConflictError,
    LoyaltyInsufficientFundsError,
    LoyaltyNetworkError,
    LoyaltyNotFoundError,
    LoyaltyRateLimitedError,
    LoyaltyServerError,
    LoyaltyValidationError,
)
from .idempotency import new_idempotency_key
from .models import (
    CompleteSaleRequest,
    CompleteSaleResponse,
    LookupCustomerRequest,
    LookupCustomerResponse,
    PreviewSaleRequest,
    PreviewSaleResponse,
    ReverseSaleRequest,
    ReverseSaleResponse,
    TransactionsFeedQuery,
    TransactionsPage,
)

_log = structlog.get_logger(__name__)

# Transient failures the retry loop should swallow. Validation / auth errors
# are deterministic — retrying them just burns the rate-limit budget.
_RETRYABLE: tuple[type[LoyaltyError], ...] = (
    LoyaltyServerError,
    LoyaltyRateLimitedError,
    LoyaltyNetworkError,
)

AuthFailureHook = Callable[[], Awaitable[bool]]
"""Async callback fired ONCE on ``LoyaltyAuthError`` (401).

Return ``True`` if recovery succeeded (e.g. token reloaded from Vault) and the
client should retry the same request once. Return ``False`` to surface the
401 to the caller. Exceptions raised by the hook propagate as-is.
"""


class LoyaltyClient:
    """Paylo POS API client (async).

    Parameters
    ----------
    base_url:
        Paylo root URL, e.g. ``https://api.paylo.az`` or ``http://localhost:8000``.
        Trailing slash is normalised away — endpoints are joined as ``/api/v1/pos/...``.
    token:
        Sanctum personal access token with the ``pos:write`` ability. Issue with
        ``php artisan pos:issue-token``. Should be loaded from Vault in production.
    timeout:
        Per-request timeout. Default 10s — Paylo's median POS endpoint latency
        is well under 100ms; 10s catches a stuck connect/TLS handshake.
    max_retries:
        Number of attempts (including the initial one) for retryable failures.
        Default 4 → 1 initial + 3 retries with 0.5s, 1s, 2s backoff.
    breaker_fail_max:
        Consecutive failures before the breaker opens. Default 5.
    breaker_reset_timeout:
        Seconds the breaker stays open before half-opening for a probe. Default 30s.
    client:
        Pre-built ``httpx.AsyncClient`` to reuse. Useful when the calling service
        already maintains a shared connection pool. The lib will not close it.
    auth_failure_hook:
        Optional async callback fired ONCE per request on 401. Return ``True``
        if you refreshed credentials (e.g. via :func:`vault_loader.rotate_client`)
        and want the client to retry once with the new token. Returning ``False``
        or omitting the hook surfaces the 401 to the caller, which is the right
        default for short-lived workflows (a sale handler should not silently
        loop on auth failures).
    hmac_secret:
        Optional hex-encoded shared secret for body signing. When set, every
        request body is signed with ``HMAC-SHA256(timestamp + "." + body)`` and
        the result is sent as ``X-Paylo-Signature: sha256=<hex>`` plus
        ``X-Paylo-Timestamp: <unix>``. The Paylo token must have been issued
        with ``--require-hmac`` and the secret matches what Paylo stored at
        token issuance time. Defends against token-leak + body-tampering MITM.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        max_retries: int = 4,
        breaker_fail_max: int = 5,
        breaker_reset_timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        auth_failure_hook: AuthFailureHook | None = None,
        hmac_secret: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_retries = max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._auth_failure_hook = auth_failure_hook
        self._hmac_secret = hmac_secret
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=breaker_fail_max,
            reset_timeout=breaker_reset_timeout,
            exclude=[
                LoyaltyAuthError,
                LoyaltyAbilityError,
                LoyaltyValidationError,
                LoyaltyIdempotencyConflictError,
                LoyaltyInsufficientFundsError,
                LoyaltyNotFoundError,
            ],
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    #
    # Public API — one method per Paylo endpoint
    #

    async def lookup_customer(self, *, qr: str) -> LookupCustomerResponse:
        """POST /api/v1/pos/customer/lookup.

        Both successful matches and misses return HTTP 200. The caller must
        branch on ``response.status`` rather than HTTP status (Paylo's
        enumeration protection — equal HTTP responses for known and unknown QRs).
        """
        payload = LookupCustomerRequest(qr=qr).model_dump()
        body = await self._request("POST", "/api/v1/pos/customer/lookup", json=payload)
        return LookupCustomerResponse.model_validate(body)

    async def preview_sale(self, request: PreviewSaleRequest) -> PreviewSaleResponse:
        """POST /api/v1/pos/sale/preview — non-committing earn/redeem calculation."""
        body = await self._request(
            "POST",
            "/api/v1/pos/sale/preview",
            json=request.model_dump(exclude_none=True),
        )
        return PreviewSaleResponse.model_validate(body)

    async def complete_sale(
        self,
        request: CompleteSaleRequest,
        *,
        idempotency_key: str | None = None,
    ) -> CompleteSaleResponse:
        """POST /api/v1/pos/sale — commit the sale and credit/debit ledger.

        ``idempotency_key`` is auto-generated if not supplied. When retrying a
        sale whose previous response was lost (network failure mid-commit),
        pass the SAME key — Paylo will replay the cached response within 24h.
        """
        key = idempotency_key or new_idempotency_key()
        body = await self._request(
            "POST",
            "/api/v1/pos/sale",
            json=request.model_dump(exclude_none=True),
            headers={"Idempotency-Key": key},
        )
        return CompleteSaleResponse.model_validate(body)

    async def reverse_sale(
        self,
        receipt_no: str,
        request: ReverseSaleRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ReverseSaleResponse:
        """POST /api/v1/pos/sale/{receipt_no}/reverse — refund the bonus side."""
        key = idempotency_key or new_idempotency_key()
        body = await self._request(
            "POST",
            f"/api/v1/pos/sale/{receipt_no}/reverse",
            json=request.model_dump(exclude_none=True),
            headers={"Idempotency-Key": key},
        )
        return ReverseSaleResponse.model_validate(body)

    async def transactions(
        self,
        query: TransactionsFeedQuery | None = None,
    ) -> TransactionsPage:
        """GET /api/v1/pos/transactions — cursor-paginated reconciliation feed.

        Use after a network-failure-after-commit retry storm to verify Paylo's
        view matches local state. See Paylo API.md §10.5 for the reconciliation
        pattern.
        """
        params = _query_params(query) if query else {}
        body = await self._request("GET", "/api/v1/pos/transactions", params=params)
        return TransactionsPage.model_validate(body)

    #
    # Internals
    #

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a single request through the retry+breaker pipeline.

        Auth header is rebuilt on each attempt so token rotation (in-place
        mutation of ``self._token`` by :func:`vault_loader.rotate_client` or
        by the ``auth_failure_hook``) is picked up by the next attempt.

        Raises a typed :class:`LoyaltyError` subclass on failure. Returns the
        parsed JSON body on success.
        """
        url = f"{self._base_url}{path}"

        try:
            return await self._run_retry_loop(method, url, json, params, headers)
        except LoyaltyAuthError:
            if self._auth_failure_hook is None:
                raise
            if not await self._auth_failure_hook():
                raise
            # One-shot recovery: hook returned True (token refreshed). Single
            # retry with the new token. Subsequent 401 surfaces — recursion is
            # NOT allowed; an indefinite retry loop on bad credentials would
            # hammer Paylo and exhaust the rate limit.
            return await self._run_retry_loop(method, url, json, params, headers)

    async def _run_retry_loop(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None,
        params: dict[str, Any] | None,
        extra_headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        """One full tenacity retry pass against ``url``. Auth header is built
        each attempt from the CURRENT ``self._token``."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=4.0),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )

        async for attempt in retrying:
            with attempt:
                body_bytes = self._encode_body(json)
                headers = self._build_headers(body_bytes is not None, extra_headers, body_bytes)
                return await self._send_one(method, url, headers, body_bytes, params)

        raise LoyaltyServerError("retry loop exited without result")  # pragma: no cover

    @staticmethod
    def _encode_body(json: dict[str, Any] | None) -> bytes | None:
        """Encode the JSON body deterministically so the bytes we sign and the
        bytes we transmit are the same. ``separators`` strips httpx's default
        spaces; ``sort_keys=False`` preserves caller order (Paylo only sees
        the signed string, ordering is opaque)."""
        if json is None:
            return None
        import json as _json

        return _json.dumps(json, separators=(",", ":")).encode("utf-8")

    def _build_headers(
        self,
        has_body: bool,
        extra: dict[str, str] | None,
        body_bytes: bytes | None,
    ) -> dict[str, str]:
        """Compose the per-attempt header set with the CURRENT bearer token,
        and (when configured) the HMAC signature pair."""
        merged: dict[str, str] = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if has_body:
            merged["Content-Type"] = "application/json"
        if self._hmac_secret is not None:
            ts = str(int(time.time()))
            payload = ts.encode("utf-8") + b"." + (body_bytes or b"")
            sig = hmac.new(self._hmac_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
            merged["X-Paylo-Timestamp"] = ts
            merged["X-Paylo-Signature"] = f"sha256={sig}"
        if extra:
            merged.update(extra)
        return merged

    async def _send_one(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body_bytes: bytes | None,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """One HTTP attempt, breaker-guarded. Maps responses to typed errors.

        Note: pybreaker's ``call_async`` requires tornado at import time, so we
        invoke the sync ``call`` API around two tiny synchronous probes — one
        before the await to check breaker state, one after to record the
        result. This drives the same state machine without dragging tornado in.
        """

        # Probe: would the breaker even let this call through right now?
        # ``call()`` with a no-op function will raise CircuitBreakerError if open.
        try:
            self._breaker.call(_breaker_probe)
        except pybreaker.CircuitBreakerError as exc:
            raise LoyaltyServerError(f"Circuit breaker open: {exc}") from exc

        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                content=body_bytes,
                params=params,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Tell the breaker — this counts as a failure.
            self._mark_breaker_failure(exc)
            raise LoyaltyNetworkError(f"Network error: {exc}") from exc

        # Successful HTTP round-trip (regardless of status code). Now map the
        # response: 2xx returns a dict, 4xx/5xx raises a typed error. We tell
        # the breaker about success (2xx) or failure (5xx, 429) — auth/validation
        # /404 are deterministic client-side issues and must NOT trip the breaker.
        try:
            body = _map_response(response)
        except LoyaltyError as exc:
            if isinstance(exc, _RETRYABLE):
                self._mark_breaker_failure(exc)
            raise

        self._breaker.call(_breaker_probe)  # record success

        _log.debug(
            "loyalty.client.request",
            method=method,
            url=url,
            status_code=response.status_code,
            idempotency_key=headers.get("Idempotency-Key"),
            idempotent_replay=response.headers.get("Idempotent-Replay"),
        )

        return body

    def _mark_breaker_failure(self, exc: BaseException) -> None:
        """Record a failure with the breaker WITHOUT changing the surfaced exception.

        ``call()`` only marks failure when the inner callable raises, so we have
        to re-raise the exception inside a closure and swallow it after."""

        def _raise() -> None:
            raise exc

        try:
            self._breaker.call(_raise)
        except BaseException:
            # Intentional: this branch fires for EVERY call (the closure always
            # raises). We're using ``call()`` purely for its failure-counting
            # side effect; the exception is the side-channel signal.
            return


def _breaker_probe() -> None:
    """Sync no-op handed to ``pybreaker.CircuitBreaker.call``.

    Returning normally tells pybreaker "this call succeeded". Used twice: as a
    pre-flight check (raises ``CircuitBreakerError`` if the breaker is open)
    and as a success-recording call after a 2xx HTTP response."""


def _map_response(response: httpx.Response) -> dict[str, Any]:
    """Convert an HTTP response into either the parsed body or a typed exception."""
    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"raw": response.text}

    if 200 <= response.status_code < 300:
        if not isinstance(body, dict):
            raise LoyaltyServerError(
                f"Expected object body, got {type(body).__name__}",
                status=response.status_code,
            )
        return body

    detail = (body.get("message") if isinstance(body, dict) else None) or response.reason_phrase
    status = response.status_code

    if status == 401:
        raise LoyaltyAuthError(detail or "Unauthorized", status=status, body=body)

    if status == 403:
        raise LoyaltyAbilityError(detail or "Forbidden", status=status, body=body)

    if status == 404:
        raise LoyaltyNotFoundError(detail or "Not found", status=status, body=body)

    if status == 422:
        field_errors = body.get("errors") if isinstance(body, dict) else None
        # Idempotency-Key conflict has a dedicated error class so the caller can
        # distinguish "client bug — wrong body" from "key reused but body OK".
        if isinstance(field_errors, dict) and "Idempotency-Key" in field_errors:
            raise LoyaltyIdempotencyConflictError(
                detail or "Idempotency-Key conflict", status=status, body=body
            )
        # Insufficient funds carries machine-readable amounts.
        if isinstance(body, dict) and body.get("status") == "insufficient_funds":
            raise LoyaltyInsufficientFundsError(
                detail or "Insufficient funds",
                available_cents=int(body.get("available_cents", 0)),
                required_cents=int(body.get("required_cents", 0)),
                body=body,
            )
        raise LoyaltyValidationError(
            detail or "Validation failed",
            status=status,
            body=body,
            field_errors=field_errors if isinstance(field_errors, dict) else None,
        )

    if status == 429:
        retry_after = int(response.headers.get("Retry-After", "1"))
        raise LoyaltyRateLimitedError(
            detail or "Rate limited",
            retry_after_seconds=retry_after,
            body=body,
        )

    if 500 <= status < 600:
        raise LoyaltyServerError(detail or "Server error", status=status, body=body)

    raise LoyaltyError(detail or f"Unexpected status {status}", status=status, body=body)


def _query_params(query: TransactionsFeedQuery) -> dict[str, str]:
    """Pydantic → flat query dict, ISO-8601 for datetimes, None values dropped."""
    out: dict[str, str] = {}
    for name, value in query.model_dump(exclude_none=True).items():
        if isinstance(value, datetime):
            out[name] = value.isoformat()
        else:
            out[name] = str(value)
    return out
