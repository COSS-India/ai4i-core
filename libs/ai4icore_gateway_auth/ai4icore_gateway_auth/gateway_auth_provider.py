"""
Gateway-trust authentication provider.

When APISIX gateway validates requests, it injects trusted headers:
  X-Validated: true
  X-User-ID: <user_id>
  X-User-Email: <email>
  X-User-Roles: <comma-separated roles>
  X-Auth-Source: AUTH_TOKEN | API_KEY | BOTH

This provider simply reads those headers and populates request.state,
preserving the same interface that routers expect.
"""
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

GATEWAY_TRUST_HEADER = "X-Validated"


class GatewayAuthProvider:
    """Lightweight auth provider that trusts gateway-injected headers."""

    @staticmethod
    async def authenticate(request: Request) -> Request:
        """Verify gateway trust header and populate request.state from injected headers."""
        validated = request.headers.get(GATEWAY_TRUST_HEADER, "").lower()
        if validated != "true":
            logger.warning("Request missing gateway validation header from %s", request.client.host if request.client else "unknown")
            raise HTTPException(status_code=401, detail="Authentication required — request must pass through API gateway")

        # Populate request.state with the same fields backend routers expect
        request.state.user_id = request.headers.get("X-User-ID")
        request.state.user_email = request.headers.get("X-User-Email")
        request.state.user_roles = [r.strip() for r in request.headers.get("X-User-Roles", "").split(",") if r.strip()]
        request.state.auth_source = request.headers.get("X-Auth-Source", "API_KEY")

        # For backward compatibility with code that checks request.state.api_key_id or .api_key_user_id
        request.state.api_key_id = request.headers.get("X-API-Key-ID")
        request.state.api_key_user_id = request.state.user_id

        return request
