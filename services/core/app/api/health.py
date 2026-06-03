"""Liveness/readiness probes (AI-1.9.1).

``/healthz`` is liveness — the process is up. ``/readyz`` is readiness — the
process can serve traffic, i.e. its Postgres and Redis dependencies answer.
Unversioned on purpose (infra endpoints, not part of the ``/v1`` API).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, str]:
    # Lifecycle gate: not-ready while starting up or draining on shutdown, so the
    # orchestrator stops routing before in-flight requests finish (graceful drain).
    if not getattr(request.app.state, "ready", False):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}

    checks: dict[str, str] = {}
    ready = True

    try:
        async with request.app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # readiness probe: any failure means not-ready, not a crash
        checks["database"] = "error"
        ready = False

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        ready = False

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", **checks}
