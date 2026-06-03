"""Domain event type constants (AI-2.H4).

Every mutating domain function emits an outbox event so the sync engine can
project the change onto external channels (Trendyol / Birmarket / Wolt). The
constants live in one place so producers and consumers never drift apart.

Naming follows ``<domain>.<aggregate>.<verb>`` (cf. ``identity.tenant.onboarded``):

* ``catalog.product.created`` — a new ``Product`` row.
* ``catalog.variant.added`` — a new ``Variant`` on an existing product.
* ``inventory.movement.applied`` — any ``StockMovement`` (kind in the payload).
* ``pricing.override.set`` — a new ``PriceOverride`` row.
"""

from __future__ import annotations

CATALOG_PRODUCT_CREATED = "catalog.product.created"
CATALOG_VARIANT_ADDED = "catalog.variant.added"
INVENTORY_MOVEMENT_APPLIED = "inventory.movement.applied"
PRICING_OVERRIDE_SET = "pricing.override.set"
