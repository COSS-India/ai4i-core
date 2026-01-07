from typing import Any, Dict, Optional, Protocol


class AuthValidator(Protocol):
    async def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        ...

    async def validate_bearer(self, token: str) -> Dict[str, Any]:
        ...


class NoOpValidator:
    """Default validator that always fails to avoid accidental open access."""

    async def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        raise RuntimeError("Auth validator not configured")

    async def validate_bearer(self, token: str) -> Dict[str, Any]:
        raise RuntimeError("Auth validator not configured")


def resolve_validator(app_state) -> AuthValidator:
    """Resolve validator from app.state or fall back to NoOp."""
    validator = getattr(app_state, "auth_validator", None)
    return validator or NoOpValidator()

