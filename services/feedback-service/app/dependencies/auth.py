"""Authentication and RBAC dependencies for the Feedback service.

AdminRequired  — requires a valid JWT with the ADMIN role (corrections, batch, query endpoints).
AuthRequired   — requires any valid JWT (telemetry ingestion endpoints callable by services/users).
"""

from ai4icore_auth.providers import create_auth_providers, build_jwt_verifier
from ai4icore_auth.dependencies import create_require_auth, create_require_role

# Standard auth providers (used where OptionalAuth is needed elsewhere)
AuthProvider, OptionalAuthProvider = create_auth_providers()

_jwt_verifier = build_jwt_verifier()

# Any valid JWT — for ingestion endpoints called by upstream services or end-users
AuthRequired = create_require_auth(_jwt_verifier)

# Admin role only — for correction, override, batch, and query endpoints
AdminRequired = create_require_role(_jwt_verifier, "ADMIN")
