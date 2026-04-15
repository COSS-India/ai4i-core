"""Authentication and RBAC dependencies for the Feedback service.

All feedback endpoints require a valid JWT with the ADMIN role.
"""

from ai4icore_auth.providers import create_auth_providers, build_jwt_verifier
from ai4icore_auth.dependencies import create_require_role

# Standard auth providers (used where OptionalAuth is needed elsewhere)
AuthProvider, OptionalAuthProvider = create_auth_providers()

# Admin-only guard — used as a FastAPI dependency on all feedback routes
_jwt_verifier = build_jwt_verifier()
AdminRequired = create_require_role(_jwt_verifier, "ADMIN")
