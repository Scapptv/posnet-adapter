"""The core service's declared feature flags (AI-1.17).

Defaults reflect the roadmap: the hub/channel capabilities are gated off until
their phases land (AI-2.5+), while baseline POS capabilities default on. Per-tenant
overrides live in the ``feature_flags`` table and are merged over these defaults.
"""

from __future__ import annotations

from libs.feature_flags import FlagRegistry, FlagSpec

REGISTRY = FlagRegistry(
    [
        FlagSpec(
            "marketplace_sync",
            default=False,
            description="Marketplace listing + stock/price sync (Birmarket/Trendyol, AI-2.5).",
        ),
        FlagSpec(
            "online_storefront",
            default=False,
            description="Customer-facing online storefront (AI-5).",
        ),
        FlagSpec(
            "delivery_integration",
            default=False,
            description="Delivery channel adapters (Wolt/Bolt-style).",
        ),
        FlagSpec(
            "multi_store",
            default=True,
            description="Allow a tenant to operate more than one store.",
        ),
    ]
)
