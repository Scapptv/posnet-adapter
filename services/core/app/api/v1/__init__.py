"""Versioned (v1) API router (AI-1.15)."""

from __future__ import annotations

from fastapi import APIRouter

from .catalog import router as catalog_router
from .feature_flags import router as feature_flags_router
from .i18n import router as i18n_router
from .roles import router as roles_router
from .tenants import router as tenants_router
from .users import router as users_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(tenants_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)
api_router.include_router(i18n_router)
api_router.include_router(feature_flags_router)
api_router.include_router(catalog_router)

__all__ = ["api_router"]
