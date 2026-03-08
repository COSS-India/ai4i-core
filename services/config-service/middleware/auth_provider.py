"""
Authentication provider for Config service routes.

Delegates to the shared GatewayAuthProvider which trusts APISIX gateway-injected
headers.  Preserves the function signatures that routers already depend on.
"""
import sys, os, logging
from fastapi import Request, Header, HTTPException
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Make the shared gateway_auth library importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "libs", "ai4icore_gateway_auth"))
from ai4icore_gateway_auth import GatewayAuthProvider

_gw = GatewayAuthProvider()


def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from Authorization header (kept for backward compatibility)."""
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    elif authorization.startswith("ApiKey "):
        return authorization[7:]
    return authorization


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
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
