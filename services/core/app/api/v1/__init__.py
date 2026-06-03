"""Versioned (v1) API router (AI-1.15)."""

from __future__ import annotations

from fastapi import APIRouter

from .tenants import router as tenants_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(tenants_router)

__all__ = ["api_router"]
