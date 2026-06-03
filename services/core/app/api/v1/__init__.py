"""Versioned (v1) API router (AI-1.15)."""

from __future__ import annotations

from fastapi import APIRouter

from .roles import router as roles_router
from .tenants import router as tenants_router
from .users import router as users_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(tenants_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)

__all__ = ["api_router"]
