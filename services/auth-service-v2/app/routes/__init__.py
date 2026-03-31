"""
Versioned API router aggregation.

Uses shared APIVersioning from ai4icore_bootstrap.
Version prefix (/api/v1) is managed centrally — route files have domain prefixes only.

Future v2: create v2 router, mount alongside v1. Deprecate v1 with Sunset header.
"""

from fastapi import APIRouter, Depends

from ai4icore_bootstrap.versioning import APIVersioning, VersionInfo

from app.core.config import settings
from app.dependencies.endpoint_guard import enforce_endpoint_permission
from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.user import router as user_router
from app.routes.role import router as role_router
from app.routes.permission import inference_router as inference_permission_router
from app.routes.permission import router as permission_router
from app.routes.api_key import router as api_key_router
from app.routes.validation import router as validation_router
from app.routes.oauth import router as oauth_router

# ── Versioning ──
versioning = APIVersioning(
    service_name=settings.service_name,
    service_version=settings.service_version,
    current_api_version=settings.api_version,
    supported_versions=[
        VersionInfo(version="v1", deprecated=False),
        # When v2 is ready:
        # VersionInfo(version="v1", deprecated=True, sunset_date="2026-12-01"),
        # VersionInfo(version="v2", deprecated=False),
    ],
)

# ── v1 routes ──
v1_router = versioning.create_router("v1")

# Public (no endpoint guard)
v1_router.include_router(auth_router)
v1_router.include_router(validation_router)
v1_router.include_router(oauth_router)

# Protected (endpoint guard enforces api_permissions.json)
_guard = [Depends(enforce_endpoint_permission)]
v1_router.include_router(user_router, dependencies=_guard)
v1_router.include_router(role_router, dependencies=_guard)
v1_router.include_router(permission_router, dependencies=_guard)
v1_router.include_router(inference_permission_router, dependencies=_guard)
v1_router.include_router(api_key_router, dependencies=_guard)

# ── Top-level router ──
api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])  # Unversioned
api_router.include_router(v1_router)
