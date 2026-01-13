from typing import Optional, Dict, Any

from fastapi import Header, Request

from .config import AuthConfig
from .exceptions import AuthenticationError, InvalidAPIKeyError, ExpiredAPIKeyError
from .utils import get_api_key_from_header
from .validators import resolve_validator


def _anonymous_context():
    return {
        "user_id": None,
        "api_key_id": None,
        "user": None,
        "api_key": None,
        "is_authenticated": False,
    }


async def 
(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """
    Shared authentication provider.
    - Reads env flags via AuthConfig
    - Uses validator on app.state.auth_validator (must be provided by service)
    """
    config = AuthConfig()  # Loads from env

    if not config.auth_enabled:
        request.state.is_authenticated = False
        return _anonymous_context()

    api_key = get_api_key_from_header(authorization)
    is_bearer = bool(authorization and authorization.startswith("Bearer "))

    if not api_key:
        if config.allow_anonymous and not config.require_api_key:
            request.state.is_authenticated = False
            return _anonymous_context()
        raise AuthenticationError("Missing API key")

    validator = resolve_validator(request.app.state)

    try:
        if is_bearer:
            auth_ctx = await validator.validate_bearer(api_key)
        else:
            auth_ctx = await validator.validate_api_key(api_key)
    except (InvalidAPIKeyError, ExpiredAPIKeyError, AuthenticationError):
        raise
    except Exception as exc:
        raise AuthenticationError(str(exc))

    # Normalize context
    user_id = auth_ctx.get("user_id")
    api_key_id = auth_ctx.get("api_key_id")
    api_key_name = auth_ctx.get("api_key_name")
    user_email = auth_ctx.get("user_email")

    request.state.user_id = user_id
    request.state.api_key_id = api_key_id
    request.state.api_key_name = api_key_name
    request.state.user_email = user_email
    request.state.is_authenticated = True

    return {
        "user_id": user_id,
        "api_key_id": api_key_id,
        "user": auth_ctx.get("user"),
        "api_key": auth_ctx.get("api_key"),
    }


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Optional[Dict[str, Any]]:
    """Authentication provider that tolerates missing/invalid credentials."""
    try:
        return await AuthProvider(request, authorization, x_auth_source)
    except AuthenticationError:
        return None


def attach_auth(app, validator) -> None:
    """
    Attach a validator to the FastAPI app so AuthProvider can use it.
    Services should call this during startup:

        from ai4icore_auth import attach_auth
        attach_auth(app, MyValidator())
    """
    app.state.auth_validator = validator

