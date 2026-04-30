"""
Health Router
Health check and monitoring endpoints
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Create router
health_router = APIRouter(
    prefix="/api/v1/language-detection",
    tags=["Health"]
)


@health_router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Service health check",
    description="Check the health of the language detection service and its dependencies"
)
async def health_check(request: Request, response: Response) -> Dict[str, Any]:
    """
    Health check endpoint for Kubernetes readiness/liveness probes.
    
    Returns:
    - 200 when core dependencies are OK
    - 503 when degraded (e.g. DB or Redis down)
    """
    redis_ok = False
    db_ok = False
    triton_ok = False
    
    # Check Redis
    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception as e:
        logger.warning(f"/health: Redis check failed: {e}")
    
    # Check DB
    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning(f"/health: PostgreSQL check failed: {e}")
    
    # Check Triton (optional - don't fail health if Triton is down)
    # Note: Triton endpoint must be resolved via Model Management - no hardcoded fallback
    triton_ok = False
    try:
        import asyncio
        from utils.triton_client import TritonClient
        # Try to get Triton endpoint from a test request if available
        # For health check, we skip Triton validation as it requires serviceId
        # Health check focuses on Redis and DB availability
        logger.debug("/health: Skipping Triton check (requires Model Management serviceId)")
    except Exception as e:
        logger.warning(f"/health: Triton check skipped: {e}")
        triton_ok = False
    
    status_str = "ok" if (redis_ok and db_ok) else "degraded"
    status_code = 200 if status_str == "ok" else 503
    
    # Set status code in response object
    response.status_code = status_code
    
    return {
        "service": "language-detection-service",
        "status": status_str,
        "redis_ok": redis_ok,
        "db_ok": db_ok,
        "triton_ok": triton_ok,
        "version": "1.0.0",
    }


@health_router.get(
    "/ready",
    response_model=Dict[str, Any],
    summary="Readiness check",
    description="Check if the service is ready to accept traffic"
)
async def readiness_check(request: Request, response: Response) -> Dict[str, Any]:
    """
    Readiness check for Kubernetes readiness probes.
    
    Similar to health check but more strict - all dependencies must be available.
    """
    redis_ok = False
    db_ok = False
    
    try:
        rc = getattr(request.app.state, "redis_client", None)
        if rc is not None:
            await rc.ping()
            redis_ok = True
    except Exception:
        pass
    
    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is not None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    
    is_ready = redis_ok and db_ok
    status_code = 200 if is_ready else 503
    
    # Set status code in response object
    response.status_code = status_code
    
    return {
        "ready": is_ready,
        "redis_ready": redis_ok,
        "db_ready": db_ok
    }


@health_router.get(
    "/live",
    response_model=Dict[str, Any],
    summary="Liveness check",
    description="Check if the service is alive (basic functionality check)"
)
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check for Kubernetes liveness probes.
    
    Simple check that the service is responding.
    """
    return {
        "alive": True,
        "service": "language-detection-service"
    }

