"""Vault-backed token resolution for the Paylo loyalty client.

Convention. Per ADR-0003 (Vault as secret authority), POSNET MUST NOT store
loyalty bearer tokens in env files or config repos. The canonical Vault path
for a merchant's POS API token is::

    vault://secret/posnet/loyalty/<merchant_code>/token

Issuance flow (operator + Vault + Paylo work together):

    1. ``php artisan pos:issue-token --merchant=m_412 --name=bravo-pos-01``
       on the Paylo host. Plain-text token is printed ONCE.
    2. Operator writes the token to Vault::

           vault kv put secret/posnet/loyalty/m_412 token=<paste>

    3. POSNET service reads it via :func:`load_token` or :func:`client_from_vault`.
       The value is never logged and never persisted outside Vault.

Rotation. To rotate, reissue the Paylo token under the same name (the previous
token is auto-deleted server-side) and overwrite the Vault KV value. POSNET
processes pick up the new token on next ``client_from_vault`` call. For
hot-rotation without restarting the calling service, see ``rotate_token`` on
the running client instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from libs.vault import VaultConfig, get_secret

from .client import LoyaltyClient

if TYPE_CHECKING:
    import httpx


def token_ref_for(merchant_code: str) -> str:
    """Return the canonical ``vault://`` reference for a merchant's POS token.

    The merchant code is the same one Paylo uses (``m_412``, ``m_209``, ...).
    No URL encoding is applied — codes are alphanumeric + underscore by Paylo
    convention.
    """
    if not merchant_code or "/" in merchant_code or " " in merchant_code:
        raise ValueError(f"invalid merchant code for vault ref: {merchant_code!r}")
    return f"vault://secret/posnet/loyalty/{merchant_code}/token"


def hmac_secret_ref_for(merchant_code: str) -> str:
    """Return the canonical ``vault://`` reference for a merchant's HMAC secret.

    Stored alongside the token at the same KV path; only the key differs.
    Operator writes::

        vault kv put secret/posnet/loyalty/m_412 token=<...> hmac_secret=<...>

    The hmac_secret key is OPTIONAL — Paylo tokens issued without
    ``--require-hmac`` don't need a paired secret and the loader returns
    ``None`` gracefully (caller must NOT assume presence).
    """
    if not merchant_code or "/" in merchant_code or " " in merchant_code:
        raise ValueError(f"invalid merchant code for vault ref: {merchant_code!r}")
    return f"vault://secret/posnet/loyalty/{merchant_code}/hmac_secret"


def load_hmac_secret(merchant_code: str, *, vault_config: VaultConfig | None = None) -> str | None:
    """Resolve the HMAC body-signing secret for ``merchant_code``, or ``None``
    if no secret is stored at that path.

    Unlike :func:`load_token`, ``SecretError`` for a missing key is suppressed
    and converted to ``None`` — HMAC is an opt-in V2 feature and most legacy
    tokens won't have a paired secret. Any OTHER Vault error (network, sealed,
    permission denied) is re-raised."""
    from libs.vault.client import SecretError  # local import to keep top-of-file lean

    try:
        return get_secret(hmac_secret_ref_for(merchant_code), config=vault_config)
    except SecretError as exc:
        # Distinguish "key not present" (benign, opt-in) from real failures.
        if "not present" in str(exc) or "secret not found" in str(exc):
            return None
        raise


def load_token(merchant_code: str, *, vault_config: VaultConfig | None = None) -> str:
    """Resolve the bearer token for ``merchant_code`` from Vault.

    Raises :class:`libs.vault.client.SecretError` if the secret is missing,
    Vault is unreachable, or the ``token`` key is absent. Callers SHOULD let
    that exception propagate — failing fast on missing credentials is better
    than silently falling back to no auth.
    """
    return get_secret(token_ref_for(merchant_code), config=vault_config)


def client_from_vault(
    merchant_code: str,
    *,
    base_url: str,
    vault_config: VaultConfig | None = None,
    timeout: float = 10.0,
    max_retries: int = 4,
    breaker_fail_max: int = 5,
    breaker_reset_timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> LoyaltyClient:
    """Construct a :class:`LoyaltyClient` whose token is loaded from Vault.

    Behaviour is identical to instantiating ``LoyaltyClient`` directly except
    the bearer token never appears in Python source. All retry / circuit-breaker
    / httpx parameters pass through unchanged.

    Token is loaded ONCE at client construction. To pick up a rotated token,
    reconstruct the client (or call :func:`rotate_client` on a running instance).
    """
    token = load_token(merchant_code, vault_config=vault_config)
    hmac_secret = load_hmac_secret(merchant_code, vault_config=vault_config)
    return LoyaltyClient(
        base_url=base_url,
        token=token,
        timeout=timeout,
        max_retries=max_retries,
        breaker_fail_max=breaker_fail_max,
        breaker_reset_timeout=breaker_reset_timeout,
        client=client,
        hmac_secret=hmac_secret,
    )


def client_from_vault_with_auto_rotation(
    merchant_code: str,
    *,
    base_url: str,
    vault_config: VaultConfig | None = None,
    timeout: float = 10.0,
    max_retries: int = 4,
    breaker_fail_max: int = 5,
    breaker_reset_timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> LoyaltyClient:
    """Like :func:`client_from_vault` but the returned client automatically
    re-reads the token from Vault on 401 and retries the request once.

    Use this for long-lived services (workers, FastAPI app servers) where the
    operator may rotate a token mid-flight: the next sale handler shrugs off
    the 401 instead of bubbling it up.

    Do NOT use for short-lived CLI / one-shot scripts — there, a 401 should
    fail loudly so the operator notices their credentials are wrong, rather
    than silently re-querying Vault and retrying.
    """
    token = load_token(merchant_code, vault_config=vault_config)
    hmac_secret = load_hmac_secret(merchant_code, vault_config=vault_config)

    # Bound the loop: if Vault returns the same token twice and Paylo still
    # rejects it, that's a real auth failure — surface it. We track the last
    # token mtime via the token string itself (Vault writes are idempotent on
    # the string value).
    last_seen_token = token

    async def reload_from_vault() -> bool:
        nonlocal last_seen_token
        fresh = load_token(merchant_code, vault_config=vault_config)
        if fresh == last_seen_token:
            # No change in Vault — refusing to retry would only burn rate limit.
            return False
        last_seen_token = fresh
        loyalty_client._token = fresh
        # HMAC secret may also have rotated alongside the token.
        loyalty_client._hmac_secret = load_hmac_secret(merchant_code, vault_config=vault_config)
        return True

    loyalty_client = LoyaltyClient(
        base_url=base_url,
        token=token,
        timeout=timeout,
        max_retries=max_retries,
        breaker_fail_max=breaker_fail_max,
        breaker_reset_timeout=breaker_reset_timeout,
        client=client,
        auth_failure_hook=reload_from_vault,
        hmac_secret=hmac_secret,
    )
    return loyalty_client


def rotate_client(
    client: LoyaltyClient, merchant_code: str, *, vault_config: VaultConfig | None = None
) -> None:
    """Reload the bearer token from Vault into an existing running client.

    Hot-rotation path — use when a long-lived service receives a 401 mid-flight
    and the operator has just pushed a fresh token to Vault. The underlying
    httpx connection pool stays open.

    Not thread-safe by design — caller must serialise concurrent rotation calls.
    """
    fresh = load_token(merchant_code, vault_config=vault_config)
    # The token is a private attribute. We mutate it in place rather than
    # exposing a setter — the client's contract is "set once at construction"
    # for normal callers; rotation is the explicit escape hatch documented here.
    client._token = fresh
