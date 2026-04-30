"""Authentication dependencies."""

from ai4icore_auth.providers import create_auth_providers

AuthProvider, OptionalAuthProvider = create_auth_providers()
