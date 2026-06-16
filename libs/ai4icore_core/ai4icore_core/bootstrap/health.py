"""
Health and readiness endpoints.

Used by ALL microservices. Returns 503 on probe failure (K8s compatible).
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from .database import get_db
from .redis import get_redis

logger = logging.getLogger(__name__)


def create_health_router(service_name: str = "service", version: str = "1.0.0") -> APIRouter:
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
        redis_client: aioredis.Redis = Depends(get_redis),
    ):
        checks: dict[str, str] = {}

        try:
            await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Readiness: database check failed: %s", exc)
            checks["database"] = "unavailable"

        try:
            await redis_client.ping()
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
