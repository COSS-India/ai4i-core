"""
Versioned API router aggregation.

Uses shared APIVersioning from ai4icore_bootstrap.
Version prefix (/api/v1) is managed centrally — route files have domain prefixes only.

Future v2: create v2 router, mount alongside v1. Deprecate v1 with Sunset header.
"""

from fastapi import APIRouter

from ai4i_core.bootstrap.versioning import APIVersioning, VersionInfo

from app.core.config import settings
from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.oauth import router as oauth_router
from app.routes.user import router as user_router
from app.routes.role import router as role_router
from app.routes.permission import inference_router as inference_permission_router
from app.routes.permission import router as permission_router
from app.routes.api_key import router as api_key_router
from app.routes.tenants import router as tenants_router
from app.routes.validation import router as validation_router
from app.routes.internal import router as internal_router
from app.routes.test_validate import router as test_validate_router

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
# Permission enforcement happens at the gateway via /auth/validate
# (api_permissions.json is the source of truth). No in-process guard.
v1_router = versioning.create_router("v1")

v1_router.include_router(auth_router)
v1_router.include_router(oauth_router)
v1_router.include_router(validation_router)
v1_router.include_router(user_router)
v1_router.include_router(role_router)
v1_router.include_router(permission_router)
v1_router.include_router(inference_permission_router)
v1_router.include_router(api_key_router)
v1_router.include_router(tenants_router)

# ── Top-level router ──
api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1/auth", tags=["Health"])
api_router.include_router(v1_router)
api_router.include_router(internal_router, prefix="/internal")
# Root path (no /api/v1 prefix), no in-app auth — load-test target for
# isolating gateway key-validation overhead from backend processing.
api_router.include_router(test_validate_router)
