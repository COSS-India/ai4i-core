"""
Authentication provider for FastAPI routes with API key validation via auth-service.
Pipeline service is stateless and uses auth-service for all validation.
"""
from fastapi import Request, Header, Depends
from typing import Optional, Dict, Any, Tuple
import logging
import httpx
import os

from middleware.exceptions import AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)

# Constants for auth service communication
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
AUTH_HTTP_TIMEOUT = float(os.getenv("AUTH_HTTP_TIMEOUT", "5.0"))


def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from Authorization header."""
    if not authorization:
        return None
    
    # Support formats: "Bearer <key>", "<key>", "ApiKey <key>"
    if authorization.startswith("Bearer "):
        return authorization[7:]
    elif authorization.startswith("ApiKey "):
        return authorization[7:]
    else:
        return authorization


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """
    Determine service name and action from request path and method.
    
    Returns:
        Tuple of (service_name, action)
        service_name: pipeline
        action: read or inference
    """
    path = request.url.path.lower()
    method = request.method.upper()
    
    # Pipeline service
    service = "pipeline"
    
    # Determine action based on path and method
    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/info" in path:
        action = "read"
    else:
        # Default to inference for POST requests
        action = "inference" if method == "POST" else "read"
    
    return service, action


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    from jose import JWTError, jwt
    
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]
    
    # JWT Configuration for local verification
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

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
        raise AuthenticationError("Invalid or expired token")
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        raise AuthenticationError("Failed to verify token")


async def validate_api_key_permissions(api_key: str, service: str, action: str) -> bool:
    """
    Validate API key has required permissions by calling auth-service.
    
    Args:
        api_key: The API key to validate
        service: Service name (pipeline)
        action: Action type (read, inference)
    
    Returns:
        True if permission is granted, False otherwise
    
    Raises:
        AuthorizationError: If permission check fails
    """
    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        
        # Call auth-service to validate permissions
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                validate_url,
                json={
                    "api_key": api_key,
                    "service": service,
                    "action": action
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("valid"):
                    return True
                else:
                    error_msg = result.get("message", "Permission denied")
                    raise AuthorizationError(error_msg)
            else:
                logger.error(f"Auth service returned status {response.status_code}: {response.text}")
                raise AuthorizationError("Failed to validate API key permissions")
                
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


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency for FastAPI routes."""
    auth_source = (x_auth_source or "API_KEY").upper()
    
    # Handle Bearer token authentication (user tokens - no permission check needed)
    if auth_source == "AUTH_TOKEN":
        return await authenticate_bearer_token(request, authorization)
    
    # Handle BOTH Bearer token AND API key (already validated by API Gateway)
    if auth_source == "BOTH":
        # Validate Bearer token to get user info
        bearer_result = await authenticate_bearer_token(request, authorization)
        
        # Extract API key
        api_key = x_api_key or get_api_key_from_header(authorization)
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Validate API key permissions via auth-service (skip database lookup)
        service, action = determine_service_and_action(request)
        await validate_api_key_permissions(api_key, service, action)
        
        # Populate request state with auth context from Bearer token
        request.state.user_id = bearer_result.get("user_id")
        request.state.api_key_id = None  # Not needed when using BOTH
        request.state.api_key_name = None
        request.state.user_email = bearer_result.get("user", {}).get("email")
        request.state.is_authenticated = True
        
        return bearer_result
    
    # Handle API key authentication (requires permission check via auth-service)
    try:
        # Extract API key from X-API-Key header first, then Authorization header
        api_key = x_api_key or get_api_key_from_header(authorization)
        
        if not api_key:
            raise AuthenticationError("Missing API key")
        
        # Determine service and action from request
        service, action = determine_service_and_action(request)
        
        # Validate API key permissions via auth-service
        await validate_api_key_permissions(api_key, service, action)
        
        # For API key only, we don't have user info from database
        # Set minimal state
        request.state.user_id = None
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = None
        request.state.is_authenticated = True
        
        # Return auth context
        return {
            "user_id": None,
            "api_key_id": None,
            "user": None,
            "api_key": None
        }
        
    except (AuthenticationError, AuthorizationError):
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise AuthenticationError("Authentication failed")


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






