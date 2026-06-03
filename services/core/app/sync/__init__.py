"""Sync layer (AI-2.H5) — bridges the domain models to the canonical model.

The canonical mapper is the seam where source-of-truth ORM rows become the
channel-agnostic ``CanonicalProduct`` / ``CanonicalInventory`` / ``CanonicalPrice``
the adapter framework will project onto external platforms (Trendyol, Birmarket,
Wolt). Channel-aware listing wiring (``channel_listings``) belongs to the
adapter SDK (AI-2.5); this layer stays channel-agnostic.
"""
