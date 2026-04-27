"""
Versioned API router aggregation for core-service.

Uses the shared APIVersioning from ai4icore_bootstrap.
The /api/v1 prefix is managed here — route files contain domain prefixes only.
"""

from fastapi import APIRouter

from ai4icore_bootstrap.versioning import APIVersioning, VersionInfo

from app.core.config import settings
from app.routes.health import router as health_router
from app.routes.model import router as model_router
from app.routes.service import router as service_router

# ── Versioning ──
versioning = APIVersioning(
    service_name=settings.service_name,
    service_version=settings.service_version,
    current_api_version=settings.api_version,
    supported_versions=[
        VersionInfo(version="v1", deprecated=False),
    ],
)

# ── v1 routes ──
v1_router = versioning.create_router("v1")
v1_router.include_router(model_router)
v1_router.include_router(service_router)

# ── Top-level router ──
api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])   # Unversioned
api_router.include_router(v1_router)
