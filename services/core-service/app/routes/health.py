"""
Health endpoint for core-service.

Only /health is exposed. Authentication and readiness probing are
handled at the gateway / infrastructure layer.
"""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}
