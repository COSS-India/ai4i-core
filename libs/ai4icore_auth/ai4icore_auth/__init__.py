"""
ai4icore_auth — Shared authentication & authorization library for AI4I-Core.

RS256 JWKS-based JWT verification, permission checking, auth middleware,
endpoint guard, and FastAPI dependencies.
Used by ALL microservices as the single source of truth for auth.
"""

from .jwt_verifier import (
    AuthClaims,
    JWTVerifier,
    JWTVerificationError,
    JWTExpiredError,
    JWTRevokedError,
)
from .permission_checker import PermissionChecker
from .middleware import AuthMiddleware
from .dependencies import (
    create_require_auth,
    create_require_permission,
    create_require_permission_code,
    create_require_role,
)
from .endpoint_guard import create_endpoint_guard
from .providers import create_auth_providers, build_jwt_verifier

__all__ = [
    "AuthClaims",
    "JWTVerifier",
    "JWTVerificationError",
    "JWTExpiredError",
    "JWTRevokedError",
    "PermissionChecker",
    "AuthMiddleware",
    "create_require_auth",
    "create_require_permission",
    "create_require_permission_code",
    "create_require_role",
    "create_endpoint_guard",
    "create_auth_providers",
    "build_jwt_verifier",
]
