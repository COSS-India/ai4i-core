"""
Health check endpoint.
"""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    """Health check for the platform core service."""
    return {"status": "healthy", "service": settings.service_name}
