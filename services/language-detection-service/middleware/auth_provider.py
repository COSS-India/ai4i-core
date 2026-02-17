"""
Authentication provider for FastAPI routes - supports JWT, API key, and BOTH with permission checks.
"""
import os
import logging
from typing import Optional, Dict, Any, Tuple

import httpx
from fastapi import Request, Header
from jose import JWTError, jwt

from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# JWT Configuration for local verification
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))


def get_api_key_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    return authorization


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()
    service = "language-detection"
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET":
        action = "read"
    else:
        action = "read"
    return service, action


async def validate_api_key_permissions(
    api_key: str,
    service: str,
    action: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Validate API key has required permissions by calling auth-service.
    If user_id is provided, auth-service will enforce that the API key belongs to that user.
    Returns the auth-service response dict.
    """
    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        payload: Dict[str, Any] = {
            "api_key": api_key,
            "service": service,
            "action": action,
        }
        if user_id is not None:
            payload["user_id"] = int(user_id)

        async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
            response = await client.post(validate_url, json=payload)

        if response.status_code == 200:
            result = response.json()
            # Enforce auth-service 'valid' flag
            if not result.get("valid", False):
                error_msg = result.get("message", "Permission denied")
                raise AuthorizationError(error_msg)

            # Optional local ownership safety net
            if user_id is not None and result.get("user_id") is not None:
                try:
                    api_key_user_id = int(result.get("user_id"))
                    requested_user_id = int(user_id)
                except (TypeError, ValueError):
                    api_key_user_id = result.get("user_id")
                    requested_user_id = user_id

                if api_key_user_id != requested_user_id:
                    raise AuthorizationError("API key does not belong to the authenticated user")

            return result

        try:
            err_json = response.json()
            err_msg = err_json.get("message") or err_json.get("detail") or response.text
        except Exception:
            err_msg = response.text
        logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
        raise AuthorizationError(err_msg or "Failed to validate API key permissions")
    except httpx.TimeoutException:
        logger.error("Timeout calling auth-service for permission validation")
        raise AuthorizationError("Permission validation service unavailable")
    except httpx.RequestError as e:
        logger.error(f"Error calling auth-service: {e}")
        raise AuthorizationError("Failed to validate API key permissions")
    except AuthorizationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating permissions: {e}")
        raise AuthorizationError("Permission validation failed")


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        # Verify JWT signature and expiry locally
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        # Extract user info from JWT claims
        user_id = payload.get("sub") or payload.get("user_id")
        email = payload.get("email", "")
        username = payload.get("username") or payload.get("email", "")
        roles = payload.get("roles", [])
        token_type = payload.get("type", "")
        
        # Ensure this is an access token
        if token_type != "access":
            raise AuthenticationError("Invalid token type")
        
        if not user_id:
            raise AuthenticationError("User ID not found in token")

        # Populate request state
        request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True
        request.state.jwt_payload = payload  # Store JWT payload for tenant resolution

        return {
            "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
            "api_key_id": None,
            "user": {
                "username": username,
                "email": email,
                "roles": roles,
            },
            "api_key": None,
        }
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        if "expired" in str(e).lower() or "exp" in str(e).lower():
            raise AuthenticationError("Authentication failed. Please log in again.")
        raise AuthenticationError("Invalid or expired token")
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        raise AuthenticationError("Failed to verify token")


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency with permission checks."""
    auth_source = (x_auth_source or "API_KEY").upper()

    if auth_source == "AUTH_TOKEN":
        # This service always requires an API key
        raise AuthenticationError("Missing API key")

    api_key = x_api_key or get_api_key_from_header(authorization)

    if auth_source == "BOTH":
        # 1) Authenticate user via JWT
        bearer_result = await authenticate_bearer_token(request, authorization)
        jwt_user_id = bearer_result.get("user_id")

        if not api_key:
            raise AuthenticationError("Missing API key")

        # 2) Validate API key + enforce ownership via auth-service (and local safety net)
        service, action = determine_service_and_action(request)
        await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)

        # 3) Populate request state with JWT identity
        request.state.user_id = jwt_user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = bearer_result.get("user", {}).get("email")
        request.state.is_authenticated = True

        return bearer_result

    # API_KEY-only mode
    if not api_key:
        raise AuthenticationError("Missing API key")

    service, action = determine_service_and_action(request)
    await validate_api_key_permissions(api_key, service, action)

    request.state.user_id = None
    request.state.api_key_id = None
    request.state.api_key_name = None
    request.state.user_email = None
    request.state.is_authenticated = True

    return {"user_id": None, "api_key_id": None, "user": None, "api_key": {"masked": True}}


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Optional[Dict[str, Any]]:
    """Optional authentication provider that doesn't raise exception if no auth provided."""
    try:
        return await AuthProvider(request, authorization, x_api_key, x_auth_source)
    except AuthenticationError:
        # Return None for optional auth
        return None
