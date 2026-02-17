"""
Health Router
FastAPI router for health check endpoints
"""

import asyncio
import logging
import os
import time
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text

from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)

# Check if health logs should be excluded
EXCLUDE_HEALTH_LOGS = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"

def _should_log_health() -> bool:
    """Check if health-related logs should be written."""
    return not EXCLUDE_HEALTH_LOGS

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
            if _should_log_health():
                logger.error(f"Redis health check failed: {e}")
            redis_status = "unhealthy"
        
        # Check PostgreSQL
        postgres_status = "healthy"
        try:
            async with request.app.state.db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            if _should_log_health():
                logger.error(f"PostgreSQL health check failed: {e}")
            postgres_status = "unhealthy"
        
        # Check Triton server
        triton_status = "healthy"
        try:
            triton_client = TritonClient(
                triton_url=request.app.state.triton_endpoint,
                api_key=request.app.state.triton_api_key,
                timeout=getattr(request.app.state, 'triton_timeout', 300.0)
            )
            if not triton_client.is_server_ready():
                triton_status = "unhealthy"
        except Exception as e:
            if _should_log_health():
                logger.error(f"Triton health check failed: {e}")
            triton_status = "unhealthy"
        
        # Determine overall status
        overall_status = "healthy" if all(
            status == "healthy" for status in [redis_status, postgres_status, triton_status]
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
        if _should_log_health():
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
        
        if not hasattr(request.app.state, 'triton_endpoint') or not request.app.state.triton_endpoint:
            raise HTTPException(status_code=503, detail="Triton endpoint not configured")
        
        # Check that Triton server is ready
        triton_client = TritonClient(
            triton_url=request.app.state.triton_endpoint,
            api_key=request.app.state.triton_api_key
        )
        
        if not triton_client.is_server_ready():
            raise HTTPException(status_code=503, detail="Triton server not ready")
        
        return {
            "status": "ready",
            "service": "llm-service",
            "version": "1.0.0",
            "timestamp": asyncio.get_event_loop().time()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if _should_log_health():
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

