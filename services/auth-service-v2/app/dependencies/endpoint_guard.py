"""
Endpoint guard — fail-closed permission enforcement.

Checks permission_ids (ints) from JWT against the api_permissions.json
mapping (resolved to DB IDs at startup).

Fail-closed: if permission map is not loaded or cache is corrupt,
requests to guarded routes are DENIED in production.
"""

import logging

from fastapi import Depends, Request

from app.core.config import settings
from app.dependencies.auth import get_current_token
from app.services.token_service import TokenPayload

logger = logging.getLogger(__name__)

_is_production = settings.environment in ("production", "staging")


async def enforce_endpoint_permission(
    request: Request,
    payload: TokenPayload = Depends(get_current_token),
) -> TokenPayload:
    from app.main import get_permission_checker
    from app.core.exceptions import InsufficientPermissionsError

    checker = get_permission_checker()

    # Fail-closed: if permission map didn't load, deny in production
    if checker is None:
        if _is_production:
            logger.error("Permission checker not loaded — denying request in production.")
            raise InsufficientPermissionsError("system", "permission-map-unavailable")
        return payload  # Dev/test: allow without map

    required_str = await checker.get_required_permission(
        request.method, request.url.path,
    )

    # No mapping for this endpoint → public, allow
    if required_str is None:
        return payload

    # Parse permission ID from cache
    try:
        required_id = int(required_str)
    except ValueError:
        logger.error(
            "Corrupt permission cache: %s:%s = '%s' (expected int). Denying.",
            request.method, request.url.path, required_str,
        )
        raise InsufficientPermissionsError(request.url.path, "corrupt-permission-cache")

    # Check permission_ids from JWT
    if required_id in payload.permission_ids:
        return payload

    # ADMIN bypass
    if "ADMIN" in payload.roles:
        return payload

    logger.warning(
        "Endpoint denied: user=%s %s:%s requires_id=%d has_ids=%s",
        payload.sub, request.method, request.url.path,
        required_id, payload.permission_ids,
    )
    raise InsufficientPermissionsError(request.url.path, request.method)
