"""Thin auth wrapper -- delegates to the shared ai4icore_auth library."""

from ai4icore_auth import (
    create_auth_provider,
    create_optional_auth_provider,
)

# Service-specific configuration
SERVICE_NAME = "language-detection"
ACTION_MAP = {"/inference": "inference"}

AuthProvider = create_auth_provider(
    service_name=SERVICE_NAME,
    action_map=ACTION_MAP,
)

OptionalAuthProvider = create_optional_auth_provider(
    service_name=SERVICE_NAME,
    action_map=ACTION_MAP,
)
