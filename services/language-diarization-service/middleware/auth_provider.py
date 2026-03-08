"""
Authentication provider for Language Diarization service routes.

Delegates to the shared GatewayAuthProvider which trusts APISIX gateway-injected
headers.  Preserves the function signatures that routers already depend on.
"""
import sys, os, logging
from fastapi import Request, Header, HTTPException
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Import from pip-installed ai4icore_gateway_auth package
# Note: Do NOT use sys.path manipulation — main.py adds /app/libs to sys.path
# which causes Python to find the package root dir as a namespace package
# instead of the actual installed package.
from ai4icore_gateway_auth import GatewayAuthProvider

_gw = GatewayAuthProvider()


def get_api_key_from_header(authorization: Optional[str]) -> Optional[str]:
    """Extract API key from Authorization header (kept for backward compatibility)."""
    if not authorization:
        return None
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    if authorization.startswith("Bearer "):
        return None
    return authorization


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency with permission checks."""
    await _gw.authenticate(request)

    return {
        "user_id": request.state.user_id,
        "api_key_id": request.state.api_key_id,
        "user": {
            "email": request.state.user_email,
            "roles": request.state.user_roles,
        } if request.state.user_email else None,
        "api_key": None,
    }


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that returns None instead of raising."""
    try:
        return await AuthProvider(request, authorization, x_api_key, x_auth_source)
    except HTTPException:
        return None
