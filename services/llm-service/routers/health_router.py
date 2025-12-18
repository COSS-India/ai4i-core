"""
Health Router
FastAPI router for health check endpoints
"""

import asyncio
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text

from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)

# Create router
health_router = APIRouter(prefix="/api/v1/llm", tags=["Health"])


@health_router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Health check endpoint",
    description="Check service health and dependencies"
)
async def health_check(request: Request) -> Dict[str, Any]:
    """Check service health and dependencies"""
    try:
        # Check Redis
        redis_status = "healthy"
        try:
            await request.app.state.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            redis_status = "unhealthy"
        
        # Check PostgreSQL
        postgres_status = "healthy"
        try:
            async with request.app.state.db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            postgres_status = "unhealthy"
        
        # Check Triton server (optional - requires Model Management serviceId)
        # Health check focuses on Redis and DB availability
        triton_status = "unknown"
        try:
            # Skip Triton check in health endpoint (requires Model Management serviceId)
            logger.debug("/health: Skipping Triton check (requires Model Management serviceId)")
        except Exception as e:
            logger.warning(f"Triton health check skipped: {e}")
            triton_status = "unknown"
        
        # Determine overall status (Triton check skipped, only Redis and DB matter)
        overall_status = "healthy" if all(
            status == "healthy" for status in [redis_status, postgres_status]
        ) else "unhealthy"
        
        response = {
            "status": overall_status,
            "service": "llm-service",
            "version": "1.0.0",
            "redis": redis_status,
            "postgres": postgres_status,
            "triton": triton_status,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        if overall_status == "unhealthy":
            raise HTTPException(status_code=503, detail=response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }
        )


@health_router.get(
    "/ready",
    response_model=Dict[str, Any],
    summary="Readiness check endpoint",
    description="Check if service is ready to accept requests"
)
async def readiness_check(request: Request) -> Dict[str, Any]:
    """Check if service is ready to accept requests"""
    try:
        # Check that all critical dependencies are initialized
        if not hasattr(request.app.state, 'redis_client') or not request.app.state.redis_client:
            raise HTTPException(status_code=503, detail="Redis client not initialized")
        
        if not hasattr(request.app.state, 'db_engine') or not request.app.state.db_engine:
            raise HTTPException(status_code=503, detail="Database engine not initialized")
        
        # Triton endpoint must be resolved via Model Management - no hardcoded fallback
        # Readiness check focuses on Redis and DB availability
        logger.debug("/ready: Skipping Triton check (requires Model Management serviceId)")
        
        return {
            "status": "ready",
            "service": "llm-service",
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


@health_router.get(
    "/live",
    response_model=Dict[str, Any],
    summary="Liveness check endpoint",
    description="Check if service is alive"
)
async def liveness_check() -> Dict[str, Any]:
    """Check if service is alive"""
    return {
        "status": "alive",
        "service": "llm-service",
        "version": "1.0.0",
        "timestamp": asyncio.get_event_loop().time()
    }

