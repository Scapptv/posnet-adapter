"""Unit tests for the auth_failure_hook one-shot recovery loop.

Covers the four meaningful states:
  1. No hook configured -> 401 surfaces immediately.
  2. Hook returns False -> 401 surfaces (refused recovery).
  3. Hook returns True -> single retry with the new token.
  4. Vault-backed auto-rotation factory: same-token-twice => no infinite loop.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from libs.loyalty_client import (
    LoyaltyAuthError,
    LoyaltyClient,
    PreviewSaleRequest,
    client_from_vault_with_auto_rotation,
)

BASE = "https://paylo.test"


@pytest.mark.unit
@respx.mock
async def test_no_hook_surfaces_401_immediately() -> None:
    """Default behaviour without a hook: 401 propagates on the first attempt."""
    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated."})
    )

    client = LoyaltyClient(base_url=BASE, token="stale", max_retries=1)
    try:
        with pytest.raises(LoyaltyAuthError):
            await client.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    finally:
        await client.aclose()

    assert route.call_count == 1


@pytest.mark.unit
@respx.mock
async def test_hook_returning_false_does_not_retry() -> None:
    """When the operator can't recover credentials, the hook MUST be able to
    say so — the client surfaces the 401 instead of looping."""
    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated."})
    )

    async def refuse() -> bool:
        return False

    client = LoyaltyClient(base_url=BASE, token="stale", max_retries=1, auth_failure_hook=refuse)
    try:
        with pytest.raises(LoyaltyAuthError):
            await client.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    finally:
        await client.aclose()

    assert route.call_count == 1


@pytest.mark.unit
@respx.mock
async def test_hook_returning_true_retries_with_new_token() -> None:
    """The hook refreshes the token in-place; the client builds the new
    Authorization header automatically and the second attempt succeeds."""

    # First call returns 401, second returns 200 with the actual payload.
    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        side_effect=[
            httpx.Response(401, json={"message": "Unauthenticated."}),
            httpx.Response(
                200,
                json={
                    "sale_amount": 5000,
                    "earn_amount": 100,
                    "redeem_amount": 0,
                    "final_to_pay": 5000,
                    "projected_balance": 100,
                },
            ),
        ]
    )

    refreshed = "fresh_token_zzzzzzzzzzzz"

    async def refresh() -> bool:
        # Rotate the client's token. The client's `_request` rebuilds the
        # Authorization header on every attempt, so the second call sees this.
        client._token = refreshed
        return True

    client = LoyaltyClient(base_url=BASE, token="stale", max_retries=1, auth_failure_hook=refresh)
    try:
        result = await client.preview_sale(
            PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
        )
    finally:
        await client.aclose()

    assert result.earn_amount == 100
    assert route.call_count == 2
    # Critical: the SECOND attempt MUST send the refreshed token, not the original.
    assert route.calls[1].request.headers["authorization"] == f"Bearer {refreshed}"


@pytest.mark.unit
@respx.mock
async def test_hook_fires_only_once_per_request() -> None:
    """If the refreshed token ALSO gets 401, we must not loop indefinitely —
    the user-visible result is a single 401 surfaced to the caller."""

    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(401, json={"message": "still bad"})
    )

    refresh_calls = 0

    async def refresh() -> bool:
        nonlocal refresh_calls
        refresh_calls += 1
        client._token = f"attempt-{refresh_calls}"
        return True

    client = LoyaltyClient(base_url=BASE, token="stale", max_retries=1, auth_failure_hook=refresh)
    try:
        with pytest.raises(LoyaltyAuthError):
            await client.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    finally:
        await client.aclose()

    assert refresh_calls == 1
    # 2 HTTP attempts (the initial one + the post-refresh retry).
    assert route.call_count == 2


@pytest.mark.unit
@respx.mock
async def test_vault_auto_rotation_refreshes_on_401_when_vault_advances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end happy path for the Vault factory: token rotated in Vault,
    auth_failure_hook reloads it, request succeeds on retry."""

    from libs.vault.client import SecretError

    tokens = iter(["old-vault-tok", "new-vault-tok"])

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return next(tokens)
        # HMAC secret path raises "not present" — this scenario is token-only.
        raise SecretError("key 'hmac_secret' not present in secret")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        side_effect=[
            httpx.Response(401, json={"message": "stale"}),
            httpx.Response(
                200,
                json={
                    "sale_amount": 5000,
                    "earn_amount": 100,
                    "redeem_amount": 0,
                    "final_to_pay": 5000,
                    "projected_balance": 100,
                },
            ),
        ]
    )

    async with client_from_vault_with_auto_rotation(
        "m_412", base_url=BASE, max_retries=1
    ) as client:
        result = await client.preview_sale(
            PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
        )

    assert result.earn_amount == 100
    assert route.calls[1].request.headers["authorization"] == "Bearer new-vault-tok"


@pytest.mark.unit
@respx.mock
async def test_vault_auto_rotation_refuses_when_vault_returns_same_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Vault returns the same token twice, the hook returns False (no point
    burning rate-limit on the same value). The 401 surfaces to the caller."""

    from libs.vault.client import SecretError

    def fake_get_secret(ref: str, *, config: object = None) -> str:
        if ref.endswith("/token"):
            return "still-stale-tok"
        raise SecretError("key 'hmac_secret' not present in secret")

    monkeypatch.setattr("libs.loyalty_client.vault_loader.get_secret", fake_get_secret)

    route = respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(401, json={"message": "Unauthenticated."})
    )

    async with client_from_vault_with_auto_rotation(
        "m_412", base_url=BASE, max_retries=1
    ) as client:
        with pytest.raises(LoyaltyAuthError):
            await client.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )

    # Only ONE HTTP attempt — the hook refused to retry because Vault was unchanged.
    assert route.call_count == 1


@pytest.mark.unit
@respx.mock
async def test_hook_not_fired_for_non_auth_errors() -> None:
    """The recovery hook is SPECIFICALLY for 401. Validation errors (422),
    rate limits (429), and 5xx must not trigger a vault round-trip."""

    respx.post(f"{BASE}/api/v1/pos/sale/preview").mock(
        return_value=httpx.Response(422, json={"message": "bad", "errors": {"x": ["y"]}})
    )

    hook_calls = 0

    async def hook() -> bool:
        nonlocal hook_calls
        hook_calls += 1
        return True

    from libs.loyalty_client import LoyaltyValidationError

    client = LoyaltyClient(base_url=BASE, token="ok", max_retries=1, auth_failure_hook=hook)
    try:
        with pytest.raises(LoyaltyValidationError):
            await client.preview_sale(
                PreviewSaleRequest(customer_id=8, sale_amount_cents=5000, use_bonus=False)
            )
    finally:
        await client.aclose()

    assert hook_calls == 0
