"""AuthProvider and OptionalAuthProvider — FastAPI dependency functions.

Usage in a service::

    from ai4icore_auth import create_auth_provider

    auth_provider = create_auth_provider(
        service_name="nmt",
        action_map={"/inference": "inference"},
    )

    @router.post("/inference")
    async def infer(auth=Depends(auth_provider)):
        ...
"""

import logging
from typing import Optional, Dict, Any, Callable, Tuple

from fastapi import Request, Header

from ai4icore_env import app_env
from ai4icore_constants.exceptions import (
    AuthenticationError,
    AuthorizationError,
)
from .headers import get_api_key_from_header
from .jwt_handler import JWTHandler
from .api_key_validator import validate_api_key_via_auth_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service & action determination
# ---------------------------------------------------------------------------

def make_action_determiner(
    service_name: str,
    action_map: Optional[Dict[str, str]] = None,
) -> Callable[[Request], Tuple[str, str]]:
    """Return a callable that maps a request to (service, action).

    *action_map* maps URL sub-paths to action names, e.g.::

        {"/inference": "inference", "/translate": "translate"}

    If no match, defaults to ``"read"``.
    """
    _map = action_map or {}

    def _determine(request: Request) -> Tuple[str, str]:
        path = request.url.path.lower()
        method = request.method.upper()
        for pattern, action in _map.items():
            if pattern in path and method == "POST":
                return service_name, action
        return service_name, "read"

    return _determine


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def create_auth_provider(
    service_name: str,
    action_map: Optional[Dict[str, str]] = None,
    determine_service_and_action: Optional[Callable] = None,
    local_api_key_lookup: Optional[Callable] = None,
    auth_enabled: bool = True,
    require_api_key: bool = True,
    allow_anonymous: bool = False,
):
    """Create an AuthProvider FastAPI dependency.

    Parameters
    ----------
    service_name : str
        Name used in permission checks (e.g. ``"asr"``, ``"nmt"``).
    action_map : dict, optional
        Path-pattern → action mapping (e.g. ``{"/inference": "inference"}``).
        Ignored when *determine_service_and_action* is provided.
    determine_service_and_action : callable, optional
        Custom ``(request) -> (service, action)`` function.
        Overrides *action_map* when provided.
    local_api_key_lookup : callable, optional
        ``async (api_key, request) -> dict`` returning
        ``{"api_key_id": ..., "user_id": ..., "api_key_name": ...}``.
        Used after auth-service validation to enrich metadata from local DB.
    auth_enabled : bool
        Master switch.  When *False* all requests pass through.
    require_api_key : bool
        Whether API key is required (read from env if not overridden).
    allow_anonymous : bool
        Allow unauthenticated requests.
    """

    jwt_handler = JWTHandler(
        secret_key=app_env.jwt_secret_key or "",
        algorithm=app_env.jwt_algorithm,
    )

    if determine_service_and_action is None:
        determine_service_and_action = make_action_determiner(
            service_name, action_map
        )

    # Read env overrides
    _auth_enabled = auth_enabled
    if app_env.auth_enabled is not None:
        _auth_enabled = str(app_env.auth_enabled).lower() in ("true", "1", "yes")

    _require_api_key = require_api_key
    if app_env.require_api_key is not None:
        _require_api_key = str(app_env.require_api_key).lower() in ("true", "1", "yes")

    _allow_anonymous = allow_anonymous or app_env.allow_anonymous_access

    async def auth_provider(
        request: Request,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    ) -> Dict[str, Any]:
        """FastAPI dependency that authenticates the request."""

        # Anonymous / disabled
        if not _auth_enabled:
            _set_anonymous_state(request)
            return _anonymous_result()

        if _allow_anonymous:
            try_it = request.headers.get("X-Try-It", "").lower()
            if try_it in ("true", "1", "yes"):
                _set_anonymous_state(request)
                return _anonymous_result()

        # Extract API key
        api_key = x_api_key or get_api_key_from_header(authorization)
        auth_source = (x_auth_source or "API_KEY").upper().strip()
        service, action = determine_service_and_action(request)

        # ── AUTH_TOKEN mode ──
        if auth_source == "AUTH_TOKEN":
            return await jwt_handler.authenticate_bearer_token(
                request, authorization
            )

        # ── BOTH mode ──
        if auth_source == "BOTH":
            return await _handle_both(
                request, authorization, api_key, service, action,
                jwt_handler,
            )

        # ── API_KEY mode (default) ──
        return await _handle_api_key(
            request, authorization, api_key, service, action,
            jwt_handler, local_api_key_lookup, _require_api_key,
        )

    return auth_provider


def create_optional_auth_provider(**kwargs):
    """Like create_auth_provider but returns None on auth failure."""

    inner = create_auth_provider(**kwargs)

    async def optional_auth_provider(
        request: Request,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
    ) -> Optional[Dict[str, Any]]:
        try:
            return await inner(
                request=request,
                authorization=authorization,
                x_api_key=x_api_key,
                x_auth_source=x_auth_source,
            )
        except (AuthenticationError, AuthorizationError):
            _set_anonymous_state(request)
            return None

    return optional_auth_provider


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _handle_both(
    request: Request,
    authorization: Optional[str],
    api_key: Optional[str],
    service: str,
    action: str,
    jwt_handler: JWTHandler,
) -> Dict[str, Any]:
    """BOTH mode: JWT + API key with ownership check."""

    # Validate JWT first
    bearer_result = await jwt_handler.authenticate_bearer_token(
        request, authorization
    )
    jwt_user_id = bearer_result.get("user_id")

    if not api_key:
        raise AuthenticationError("API key required in BOTH mode")

    # Validate API key via auth-service with user_id for ownership
    await validate_api_key_via_auth_service(
        api_key=api_key,
        service=service,
        action=action,
        auth_service_url=app_env.auth_service_url,
        auth_http_timeout=app_env.auth_http_timeout,
        user_id=jwt_user_id,
    )

    # JWT identity is primary
    return bearer_result


async def _handle_api_key(
    request: Request,
    authorization: Optional[str],
    api_key: Optional[str],
    service: str,
    action: str,
    jwt_handler: JWTHandler,
    local_api_key_lookup: Optional[Callable],
    require_api_key: bool,
) -> Dict[str, Any]:
    """API_KEY mode: validate via auth-service, optionally enrich from local DB."""

    # Some services extract tenant info from Bearer token even in API_KEY mode
    if authorization and authorization.startswith("Bearer "):
        try:
            await jwt_handler.authenticate_bearer_token(
                request, authorization
            )
        except AuthenticationError:
            pass  # JWT is optional in API_KEY mode

    if not api_key:
        if require_api_key:
            raise AuthenticationError("API key is required")
        _set_anonymous_state(request)
        return _anonymous_result()

    # Validate via auth-service
    auth_result = await validate_api_key_via_auth_service(
        api_key=api_key,
        service=service,
        action=action,
        auth_service_url=app_env.auth_service_url,
        auth_http_timeout=app_env.auth_http_timeout,
    )

    user_id = auth_result.get("user_id")
    api_key_id = auth_result.get("api_key_id")
    api_key_name = auth_result.get("api_key_name")
    user_email = auth_result.get("user_email")

    # Optionally enrich from local DB
    if local_api_key_lookup:
        try:
            local_info = await local_api_key_lookup(api_key, request)
            if local_info:
                api_key_id = local_info.get("api_key_id", api_key_id)
                user_id = local_info.get("user_id", user_id)
                api_key_name = local_info.get("api_key_name", api_key_name)
                user_email = local_info.get("user_email", user_email)
        except Exception as exc:
            logger.debug("Local API key lookup failed: %s", exc)

    # Populate request state
    request.state.user_id = user_id
    request.state.api_key_id = api_key_id
    request.state.api_key_name = api_key_name
    request.state.user_email = user_email
    request.state.is_authenticated = True

    return {
        "user_id": user_id,
        "api_key_id": api_key_id,
        "user": {"id": user_id, "email": user_email} if user_id else None,
        "api_key": {"id": api_key_id, "name": api_key_name} if api_key_id else None,
    }


def _set_anonymous_state(request: Request) -> None:
    request.state.user_id = None
    request.state.api_key_id = None
    request.state.api_key_name = None
    request.state.user_email = None
    request.state.is_authenticated = False


def _anonymous_result() -> Dict[str, Any]:
    return {
        "user_id": None,
        "api_key_id": None,
        "user": None,
        "api_key": None,
    }
