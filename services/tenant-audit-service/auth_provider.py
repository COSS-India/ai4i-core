"""Thin auth wrapper -- delegates to the shared ai4icore_auth library.

Multi-tenant defaults to AUTH_TOKEN (Bearer JWT) -- API key is not required
by default.  The library's ``auth_enabled`` / ``allow_anonymous`` env
overrides are respected.
"""

from ai4icore_auth import (
    create_auth_provider,
    create_optional_auth_provider,
)

# Service-specific configuration
SERVICE_NAME = "tenant-audit-service"

AuthProvider = create_auth_provider(
    service_name=SERVICE_NAME,
    require_api_key=False,  # JWT only by default
    allow_anonymous=False,  # do not allow anonymous access
)

OptionalAuthProvider = create_optional_auth_provider(
    service_name=SERVICE_NAME,
    require_api_key=False,
    allow_anonymous=False,
)
