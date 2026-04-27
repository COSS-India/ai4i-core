"""
Health & readiness endpoints — re-exported from shared ai4icore_bootstrap.
"""

from ai4icore_bootstrap.health import create_health_router

from app.core.config import settings


router = create_health_router(
    service_name=settings.service_name,
    version=settings.service_version,
)
