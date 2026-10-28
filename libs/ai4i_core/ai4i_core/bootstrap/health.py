"""
Health and readiness endpoints.

Used by ALL microservices. Returns 503 on probe failure (K8s compatible).
"""

import logging
from collections.abc import Callable
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .redis import get_redis_client as _default_get_redis_client

logger = logging.getLogger(__name__)


def create_health_router(
    service_name: str = "service",
    version: str = "1.0.0",
    get_redis_client: Optional[Callable] = None,
) -> APIRouter:
    """
    Create a health router with /, /health, /ready endpoints.
    The /ready endpoint checks DB and Redis connectivity.
    """
    router = APIRouter()

    @router.get("/")
    async def root():
        return {"service": service_name, "version": version, "status": "running"}

    @router.get("/health")
    async def health():
        return {"status": "healthy"}

    @router.get("/ready")
    async def readiness(
        db: AsyncSession = Depends(get_db),
    ):
        checks: dict[str, str] = {}

        try:
            await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Readiness: database check failed: %s", exc)
            checks["database"] = "unavailable"

        try:
            _get_client = get_redis_client or _default_get_redis_client
            rc = _get_client()
            await rc.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.warning("Readiness: redis check failed: %s", exc)
            checks["redis"] = "unavailable"

        all_ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"success": True, "data": {"ready": all_ok, "checks": checks}},
        )

    return router
