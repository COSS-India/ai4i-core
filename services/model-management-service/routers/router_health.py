"""
Health Router
FastAPI router for health check endpoints (Model Management Service)
"""

import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text

from logger import logger

router_health = APIRouter(tags=["Health"])


@router_health.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Health check endpoint",
    description="Check health of service and all dependencies"
)
async def health_check(request: Request) -> Dict[str, Any]:
    """Comprehensive health check"""

 
    redis_status = "healthy"
    try:
        redis = request.app.state.redis_client
        if redis:
            redis.ping()
        else:
            redis_status = "unhealthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

  
    auth_db_status = "healthy"
    try:
        async with request.app.state.auth_db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Auth DB health check failed: {e}")
        auth_db_status = "unhealthy"


    model_db_status = "healthy"
    try:
        async with request.app.state.app_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Model Management DB health check failed: {e}")
        model_db_status = "unhealthy"

  
    overall_status = "healthy" if all(
        [
            redis_status == "healthy",
            auth_db_status == "healthy",
            model_db_status == "healthy"
        ]
    ) else "unhealthy"

    response = {
        "status": overall_status,
        "service": "model-management-service",
        "version": "1.0.0",
        "redis": redis_status,
        "auth_db": auth_db_status,
        "model_management_db": model_db_status,
        "timestamp": asyncio.get_event_loop().time()
    }

    if overall_status == "unhealthy":
        raise HTTPException(status_code=503, detail=response)

    return response



@router_health.get(
    "/ready",
    response_model=Dict[str, Any],
    summary="Readiness check endpoint",
    description="Checks if service is ready to accept traffic"
)
async def readiness_check(request: Request) -> Dict[str, Any]:
    """Readiness check"""

    try:
        # Redis initialized
        if not hasattr(request.app.state, "redis_client") or not request.app.state.redis_client:
            raise HTTPException(status_code=503, detail="Redis client not initialized")

        # Auth DB engine initialized
        if not hasattr(request.app.state, "auth_db_engine") or not request.app.state.auth_db_engine:
            raise HTTPException(status_code=503, detail="Auth DB engine not initialized")

        # Model DB engine initialized
        if not hasattr(request.app.state, "app_db_engine") or not request.app.state.app_db_engine:
            raise HTTPException(status_code=503, detail="Model Management DB engine not initialized")

        return {
            "status": "ready",
            "service": "model-management-service",
            "version": "1.0.0",
            "timestamp": asyncio.get_event_loop().time()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }
        )


@router_health.get(
    "/live",
    response_model=Dict[str, Any],
    summary="Liveness check endpoint",
    description="Basic check to confirm service is running"
)
async def liveness_check() -> Dict[str, Any]:
    """Simple liveness check"""
    return {
        "status": "alive",
        "service": "model-management-service",
        "version": "1.0.0",
        "timestamp": asyncio.get_event_loop().time()
    }
