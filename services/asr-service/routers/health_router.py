"""
FastAPI router for health check endpoints.

Adapted from Ai4V-C health check patterns.
"""

import logging
import time
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status, Request
from sqlalchemy import text

logger = logging.getLogger(__name__)

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
    # Get connections from app state (initialized in lifespan)
    redis_client = getattr(request.app.state, "redis_client", None)
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    
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
        logger.error(f"Redis health check failed: {e}")
        health_status["redis"] = "unhealthy"
    
    # Check PostgreSQL connectivity
    try:
        if db_session_factory:
            async with db_session_factory() as session:
                await session.execute(text("SELECT 1"))
            health_status["postgres"] = "healthy"
        else:
            health_status["postgres"] = "unavailable"
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        health_status["postgres"] = "unhealthy"
    
    # Check Triton server connectivity
    try:
        import tritonclient.http as http_client
        import os
        
        triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
        # Strip scheme from URL if present (Triton client expects host:port format)
        if triton_url.startswith(('http://', 'https://')):
            triton_url = triton_url.split('://', 1)[1]
        client = http_client.InferenceServerClient(url=triton_url)
        
        if client.is_server_ready():
            health_status["triton"] = "healthy"
        else:
            health_status["triton"] = "unhealthy"
    except ImportError:
        health_status["triton"] = "unhealthy"
    except Exception as e:
        logger.warning(f"Triton health check failed: {e}")
        health_status["triton"] = "unhealthy"
    
    # Determine overall status
    if (health_status["redis"] == "healthy" and 
        health_status["postgres"] == "healthy" and 
        health_status["triton"] == "healthy"):
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "unhealthy"
    
    # Always return 200 with status in JSON body for health monitoring
    # Health monitors check JSON status, not HTTP status code
    # This allows the service to report its state even when dependencies are down
    return health_status


@health_router.get(
    "/ready",
    response_model=Dict[str, Any],
    summary="Readiness check endpoint",
    description="Check if service is ready to accept requests"
)
async def readiness_check(request: Request) -> Dict[str, Any]:
    """Check if service is ready to accept requests."""
    # Get connections from app state (initialized in lifespan)
    redis_client = getattr(request.app.state, "redis_client", None)
    db_session_factory = getattr(request.app.state, "db_session_factory", None)
    
    readiness_status = {
        "status": "ready",
        "service": "asr-service",
        "version": "1.0.0",
        "timestamp": time.time()
    }
    
    # Check critical dependencies
    try:
        # Check if database is available
        if not db_session_factory:
            readiness_status["status"] = "not_ready"
            readiness_status["reason"] = "Database not initialized"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=readiness_status
            )
        
        # Check if Redis is available
        if not redis_client:
            readiness_status["status"] = "not_ready"
            readiness_status["reason"] = "Redis not initialized"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=readiness_status
            )
        
        # Test database connection
        async with db_session_factory() as session:
            await session.execute(text("SELECT 1"))
        
        # Test Redis connection
        await redis_client.ping()
        
        # Check if Triton server has models loaded (optional)
        try:
            import tritonclient.http as http_client
            import os
            
            triton_url = os.getenv("TRITON_ENDPOINT", "http://localhost:8000")
            # Strip scheme from URL if present (Triton client expects host:port format)
            if triton_url.startswith(('http://', 'https://')):
                triton_url = triton_url.split('://', 1)[1]
            client = http_client.InferenceServerClient(url=triton_url)
            
            if not client.is_server_ready():
                readiness_status["status"] = "not_ready"
                readiness_status["reason"] = "Triton server not ready"
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=readiness_status
                )
        except ImportError:
            # Triton client not available, but that's okay for readiness
            pass
        except Exception as e:
            logger.warning(f"Triton readiness check failed: {e}")
            # Don't fail readiness for Triton issues
        
        return readiness_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        readiness_status["status"] = "not_ready"
        readiness_status["reason"] = str(e)
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
