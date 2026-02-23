"""
FastAPI router for health check endpoints.

Adapted from Ai4V-C health check patterns.
"""

import logging
import os
import time
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from middleware.exceptions import ErrorDetail
from services.constants.error_messages import SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE_MESSAGE
from fastapi import Request

# Don't import from main at module level to avoid circular imports
# Instead, access redis_client and db_engine through app state in the route handlers

logger = logging.getLogger(__name__)

# Check if health logs should be excluded
EXCLUDE_HEALTH_LOGS = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"

def _should_log_health() -> bool:
    """Check if health-related logs should be written."""
    return not EXCLUDE_HEALTH_LOGS

# Create router
health_router = APIRouter(prefix="/api/v1/asr", tags=["Health"])


@health_router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Health check endpoint",
    description="Check service health and dependencies"
)
async def health_check(request: Request) -> Dict[str, Any]:
    """Comprehensive health check for service and dependencies."""
    # Access redis_client and db_engine from app state to avoid circular imports
    redis_client = getattr(request.app.state, 'redis_client', None)
    db_engine = getattr(request.app.state, 'db_engine', None)
    
    health_status = {
        "status": "healthy",
        "service": "asr-service",
        "version": "1.0.0",
        "redis": "unhealthy",
        "postgres": "unhealthy",
        "triton": "unhealthy",
        "timestamp": time.time()
    }
    
    # Check Redis connectivity
    try:
        if redis_client:
            await redis_client.ping()
            health_status["redis"] = "healthy"
        else:
            health_status["redis"] = "unavailable"
    except Exception as e:
        if _should_log_health():
            logger.error(f"Redis health check failed: {e}")
        health_status["redis"] = "unhealthy"
    
    # Check PostgreSQL connectivity
    try:
        if db_engine:
            async with db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            health_status["postgres"] = "healthy"
        else:
            health_status["postgres"] = "unavailable"
    except Exception as e:
        if _should_log_health():
            logger.error(f"PostgreSQL health check failed: {e}")
        health_status["postgres"] = "unhealthy"
    
    # Check Triton server connectivity
    try:
        import tritonclient.http as http_client
        import os
        
        # Triton endpoint must be resolved via Model Management - no hardcoded fallback
        # Skip Triton check in health endpoint (requires Model Management serviceId)
        if _should_log_health():
            logger.debug("/health: Skipping Triton check (requires Model Management serviceId)")
        
        if client.is_server_ready():
            health_status["triton"] = "healthy"
        else:
            health_status["triton"] = "unhealthy"
    except ImportError:
        health_status["triton"] = "unhealthy"
    except Exception as e:
        if _should_log_health():
            logger.warning(f"Triton health check failed: {e}")
        health_status["triton"] = "unhealthy"
    
    # Determine overall status
    if (health_status["redis"] == "healthy" and 
        health_status["postgres"] == "healthy" and 
        health_status["triton"] == "healthy"):
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "unhealthy"
    
    # Return appropriate status code
    if health_status["status"] == "unhealthy":
        error_detail = ErrorDetail(
            message=SERVICE_UNAVAILABLE_MESSAGE,
            code=SERVICE_UNAVAILABLE
        )
        # Include health status details in the error
        health_status["error"] = error_detail.dict()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status
        )
    
    return health_status


@health_router.get(
    "/ready",
    response_model=Dict[str, Any],
    summary="Readiness check endpoint",
    description="Check if service is ready to accept requests"
)
async def readiness_check(request: Request) -> Dict[str, Any]:
    """Check if service is ready to accept requests."""
    # Access redis_client and db_engine from app state to avoid circular imports
    redis_client = getattr(request.app.state, 'redis_client', None)
    db_engine = getattr(request.app.state, 'db_engine', None)
    
    readiness_status = {
        "status": "ready",
        "service": "asr-service",
        "version": "1.0.0",
        "timestamp": time.time()
    }
    
    # Check critical dependencies
    try:
        # Check if database is available
        if not db_engine:
            readiness_status["status"] = "not_ready"
            readiness_status["reason"] = "Database not initialized"
            error_detail = ErrorDetail(
                message=SERVICE_UNAVAILABLE_MESSAGE,
                code=SERVICE_UNAVAILABLE
            )
            readiness_status["error"] = error_detail.dict()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=readiness_status
            )
        
        # Check if Redis is available
        if not redis_client:
            readiness_status["status"] = "not_ready"
            readiness_status["reason"] = "Redis not initialized"
            error_detail = ErrorDetail(
                message=SERVICE_UNAVAILABLE_MESSAGE,
                code=SERVICE_UNAVAILABLE
            )
            readiness_status["error"] = error_detail.dict()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=readiness_status
            )
        
        # Test database connection
        async with db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        # Test Redis connection
        await redis_client.ping()
        
        # Check if Triton server has models loaded (optional)
        try:
            import tritonclient.http as http_client
            import os
            
            # Triton endpoint must be resolved via Model Management - no hardcoded fallback
            # Skip Triton check in readiness endpoint (requires Model Management serviceId)
            if _should_log_health():
                logger.debug("/ready: Skipping Triton check (requires Model Management serviceId)")
            # Skip Triton validation - only check Redis and DB

        except Exception as e:
            if _should_log_health():
                logger.warning(f"Triton readiness check skipped: {e}")
            # Triton client not available, but that's okay for readiness
            pass
        except Exception as e:
            if _should_log_health():
                logger.warning(f"Triton readiness check failed: {e}")
            # Don't fail readiness for Triton issues
        
        return readiness_status
        
    except HTTPException:
        raise
    except Exception as e:
        if _should_log_health():
            logger.error(f"Readiness check failed: {e}")
        readiness_status["status"] = "not_ready"
        readiness_status["reason"] = str(e)
        error_detail = ErrorDetail(
            message=SERVICE_UNAVAILABLE_MESSAGE,
            code=SERVICE_UNAVAILABLE
        )
        readiness_status["error"] = error_detail.dict()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=readiness_status
        )


@health_router.get(
    "/live",
    response_model=Dict[str, Any],
    summary="Liveness check endpoint",
    description="Check if service is alive"
)
async def liveness_check() -> Dict[str, Any]:
    """Simple liveness check that always returns 200."""
    return {
        "status": "alive",
        "service": "asr-service",
        "version": "1.0.0",
        "timestamp": time.time()
    }
