"""
Standard health/ready/live endpoints for inference services.

Usage:
    from ai4icore_service_base import create_health_router

    health_router = create_health_router(service_name="nmt-service", version="1.0.0")
    app.include_router(health_router)
"""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_health_router(
    service_name: str,
    version: str = "1.0.0",
    prefix: str = "",
) -> APIRouter:
    """
    Create a health router with /health, /ready, and /live endpoints.

    Checks Redis and PostgreSQL connectivity from ``app.state``.
    """
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/health")
    async def health_check(request: Request) -> JSONResponse:
        """Full dependency health check (Redis + PostgreSQL)."""
        checks: dict = {}
        overall = True

        # Redis
        redis_client = getattr(request.app.state, "redis_client", None)
        if redis_client:
            try:
                await redis_client.ping()
                checks["redis"] = "healthy"
            except Exception as e:
                checks["redis"] = f"unhealthy: {e}"
                overall = False
        else:
            checks["redis"] = "not configured"

        # PostgreSQL
        db_engine = getattr(request.app.state, "db_engine", None)
        if db_engine:
            try:
                from sqlalchemy import text
                async with db_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                checks["database"] = "healthy"
            except Exception as e:
                checks["database"] = f"unhealthy: {e}"
                overall = False
        else:
            checks["database"] = "not configured"

        status_code = 200 if overall else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if overall else "degraded",
                "service": service_name,
                "version": version,
                "timestamp": time.time(),
                "checks": checks,
            },
        )

    @router.get("/ready")
    async def readiness_check(request: Request) -> JSONResponse:
        """Readiness probe -- service can accept traffic."""
        db_engine = getattr(request.app.state, "db_engine", None)
        if db_engine:
            try:
                from sqlalchemy import text
                async with db_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception:
                return JSONResponse(status_code=503, content={"ready": False})
        return JSONResponse(status_code=200, content={"ready": True})

    @router.get("/live")
    async def liveness_check() -> JSONResponse:
        """Liveness probe -- process is alive."""
        return JSONResponse(status_code=200, content={"alive": True})

    return router
