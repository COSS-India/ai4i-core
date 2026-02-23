"""
Authentication provider for FastAPI routes - supports JWT, API key, and BOTH with permission checks.
Performs local JWT verification and calls auth-service for API key permission validation.
"""
import os
import logging
from typing import Optional, Dict, Any, Tuple

import httpx
from fastapi import Request, Header
from jose import JWTError, jwt

from middleware.exceptions import AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError

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
    service = "speaker-diarization"
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
    Returns the auth-service response dict on success.
    """
    # Explicitly handle missing API key BEFORE talking to auth-service
    if not api_key:
        raise InvalidAPIKeyError("API key is missing. Please provide a valid API key in the X-API-Key header or Authorization header.")

    try:
        validate_url = f"{AUTH_SERVICE_URL}/api/v1/auth/validate-api-key"
        payload: Dict[str, Any] = {
            "api_key": api_key,
            "service": service,
            "action": action,
        }
        if user_id is not None:
            payload["user_id"] = user_id

        async with httpx.AsyncClient(timeout=AUTH_HTTP_TIMEOUT) as client:
            response = await client.post(validate_url, json=payload)

        if response.status_code == 200:
            result = response.json()
            if result.get("valid"):
                # API key is valid - check ownership if user_id provided
                if user_id is not None and result.get("user_id") is not None:
                    try:
                        api_key_user_id = int(result.get("user_id"))
                        requested_user_id = int(user_id)
                        if api_key_user_id != requested_user_id:
                            logger.error(f"API key ownership mismatch: requested_user_id={requested_user_id}, api_key_user_id={api_key_user_id}")
                            raise AuthorizationError("API key does not belong to the authenticated user")
                    except (TypeError, ValueError):
                        # If conversion fails, log warning but don't fail
                        logger.warning(f"Could not compare user_ids: requested={user_id}, api_key={result.get('user_id')}")
                return result

            # API key invalid - extract detailed reason from auth-service
            error_msg = result.get("message", "Permission denied")
            error_code = result.get("code", "PERMISSION_DENIED")
            error_reason = result.get("reason", "unknown")
            
            # Provide specific error messages based on the reason
            if error_reason == "api_key_not_found" or error_code == "API_KEY_NOT_FOUND":
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                raise InvalidAPIKeyError(f"Invalid API key: {error_msg}")
            elif error_reason == "api_key_expired" or error_code == "API_KEY_EXPIRED":
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                raise ExpiredAPIKeyError(f"API key has expired: {error_msg}")
            elif error_reason == "api_key_inactive" or error_code == "API_KEY_INACTIVE":
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                raise InvalidAPIKeyError(f"API key is inactive: {error_msg}")
            elif error_reason == "permission_denied" or error_code == "PERMISSION_DENIED":
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                # If the message is about invalid API key, use it as-is without prefix
                if "invalid api key" in error_msg.lower():
                    raise AuthorizationError(error_msg)
                raise AuthorizationError(f"Permission denied: {error_msg}")
            elif error_reason == "ownership_mismatch" or "does not belong" in error_msg.lower():
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                raise AuthorizationError(f"API key ownership mismatch: {error_msg}")
            else:
                logger.error(
                    "Auth-service rejected API key: reason=%s code=%s message=%s",
                    error_reason,
                    error_code,
                    error_msg,
                )
                raise AuthorizationError(error_msg)

        # Handle non-200 responses - extract error from detail or message field
        try:
            error_data = response.json()
            # FastAPI HTTPException uses "detail" field, auth-service uses "message"
            err_msg = error_data.get("detail") or error_data.get("message") or response.text
        except Exception:
            err_msg = response.text
        
        logger.error(f"Auth service returned status {response.status_code}: {err_msg}")
        
        # Provide specific error messages based on status code
        if response.status_code == 400:
            raise InvalidAPIKeyError(f"Invalid API key request: {err_msg or 'Bad request to authentication service'}")
        elif response.status_code == 401:
            raise InvalidAPIKeyError(f"Invalid API key: {err_msg or 'Authentication failed'}")
        elif response.status_code == 403:
            # If the message is about invalid API key, use it as-is without prefix
            if err_msg and "invalid api key" in err_msg.lower():
                raise AuthorizationError(err_msg)
            raise AuthorizationError(f"Permission denied: {err_msg or 'Access forbidden'}")
        elif response.status_code == 404:
            raise InvalidAPIKeyError(f"API key not found: {err_msg or 'The provided API key does not exist'}")
        elif response.status_code >= 500:
            raise AuthorizationError(f"Authentication service error: {err_msg or 'Internal server error in authentication service'}")
        else:
            raise AuthorizationError(f"Failed to validate API key permissions: {err_msg or 'Unknown error from authentication service'}")
    except httpx.TimeoutException:
        logger.error("Timeout calling auth-service for permission validation")
        raise AuthorizationError("Permission validation service unavailable. The authentication service did not respond in time. Please try again later.")
    except httpx.RequestError as e:
        logger.error(f"Error calling auth-service: {e}")
        raise AuthorizationError(f"Failed to validate API key permissions: Unable to connect to authentication service. {str(e)}")
    except (InvalidAPIKeyError, ExpiredAPIKeyError, AuthorizationError):
        # Re-raise explicit authorization failures without wrapping
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating permissions: {e}", exc_info=True)
        raise AuthorizationError(f"Permission validation failed: An unexpected error occurred while validating API key permissions. {str(e)}")


async def authenticate_bearer_token(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    """
    Validate JWT access token locally (signature + expiry check).
    Kong already validated the token, this is a defense-in-depth check.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token. Please provide a valid JWT token in the Authorization header with 'Bearer ' prefix.")

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
            raise AuthenticationError(f"Invalid token type: Expected 'access' token, but received '{token_type}'. Please use a valid access token.")
        
        if not user_id:
            raise AuthenticationError("User ID not found in token. The JWT token does not contain a valid user identifier.")

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
        error_str = str(e).lower()
        logger.warning(f"JWT verification failed: {e}")
        
        # Provide specific error messages for different JWT errors
        if "expired" in error_str or "exp" in error_str:
            raise AuthenticationError("Authentication failed. Your session has expired. Please log in again.")
        elif "signature" in error_str or "invalid" in error_str:
            raise AuthenticationError("Invalid token: The JWT token signature is invalid or the token is malformed.")
        elif "not enough segments" in error_str or "malformed" in error_str:
            raise AuthenticationError("Invalid token format: The JWT token is malformed. Please provide a valid token.")
        else:
            raise AuthenticationError(f"Invalid or expired token: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}", exc_info=True)
        raise AuthenticationError(f"Failed to verify token: An unexpected error occurred during token verification. {str(e)}")


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
        raise AuthenticationError("Missing API key. This service requires an API key for authentication. Please provide a valid API key in the X-API-Key header or Authorization header.")

    api_key = x_api_key or get_api_key_from_header(authorization)

    if auth_source == "BOTH":
        try:
            # 1) Authenticate via JWT
            bearer_result = await authenticate_bearer_token(request, authorization)
            jwt_user_id = bearer_result.get("user_id")

            if not api_key:
                raise InvalidAPIKeyError("Missing API key. In BOTH authentication mode, both a JWT token and an API key are required. Please provide a valid API key in the X-API-Key header or Authorization header.")

            # 2) Validate API key + permissions via auth-service (single source of truth),
            # passing jwt_user_id so auth-service can enforce ownership.
            service, action = determine_service_and_action(request)
            auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)

            # CRITICAL: Always check valid field - auth-service may return valid=false for ownership mismatch
            if not auth_result.get("valid", False):
                error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                logger.error(f"Auth-service returned valid=false in BOTH mode: {error_msg}, jwt_user_id={jwt_user_id}, api_key_user_id={auth_result.get('user_id')}")
                
                # In BOTH mode, if we provided user_id and auth-service returned valid=false,
                # it's ALWAYS an ownership issue (API key doesn't belong to the authenticated user)
                # This matches OCR behavior: when user_id is provided in BOTH mode and valid=false,
                # it means the API key doesn't belong to that user, regardless of the error message
                if jwt_user_id is not None:
                    # Check if user_id was provided and auth-service returned a different user_id
                    if auth_result.get("user_id") is not None:
                        try:
                            api_key_user_id = int(auth_result.get("user_id"))
                            requested_user_id = int(jwt_user_id)
                            if api_key_user_id != requested_user_id:
                                logger.error(f"API key ownership mismatch: requested_user_id={requested_user_id}, api_key_user_id={api_key_user_id}")
                                raise AuthenticationError("API key does not belong to the authenticated user")
                        except (TypeError, ValueError):
                            pass  # If conversion fails, fall through
                    
                    # In BOTH mode with user_id provided, valid=false ALWAYS means ownership issue
                    # regardless of what the error message says (e.g., "Invalid API key: This key does not have access...")
                    logger.error(f"BOTH mode: valid=false with user_id={jwt_user_id} provided, treating as ownership issue")
                    raise AuthenticationError("API key does not belong to the authenticated user")
                
                # For other errors (when user_id not provided), preserve the message
                raise AuthenticationError(error_msg)

            # 3) Populate request.state – keep JWT as primary identity (matching ASR/TTS/NMT)
            request.state.user_id = jwt_user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = bearer_result.get("user", {}).get("email")
            request.state.is_authenticated = True

            return bearer_result
        except (InvalidAPIKeyError, ExpiredAPIKeyError) as e:
            # Preserve specific API key error messages
            logger.error(f"Speaker-diarization BOTH mode: API key error: {e}")
            raise
        except AuthenticationError as e:
            # Preserve authentication error messages (including ownership errors)
            # The error handler will format them correctly
            logger.error(f"Speaker-diarization BOTH mode: Authentication error: {e}")
            raise
        except AuthorizationError as e:
            # Convert AuthorizationError to AuthenticationError in BOTH mode to match OCR behavior
            # The error handler will format them correctly
            error_msg = str(e) if e else "API key does not belong to the authenticated user"
            logger.error(f"Speaker-diarization BOTH mode: Authorization error converted to AuthenticationError: {error_msg}")
            raise AuthenticationError(error_msg)
        except Exception as e:
            logger.error(f"Speaker-diarization BOTH mode: Unexpected error: {e}", exc_info=True)
            # Even on unexpected errors we provide a helpful message
            raise AuthenticationError(f"Authentication failed: An unexpected error occurred during authentication. {str(e)}")

    if not api_key:
        raise InvalidAPIKeyError("Missing API key. Please provide a valid API key in the X-API-Key header or Authorization header.")

    service, action = determine_service_and_action(request)
    auth_result = await validate_api_key_permissions(api_key, service, action)
    # Check if auth-service returned valid=false
    if not auth_result.get("valid", False):
        error_msg = auth_result.get("message", "Permission denied")
        logger.error(f"Auth-service returned valid=false for API_KEY mode: {error_msg}")
        # If the message is about invalid API key, use it as-is without prefix
        if "invalid api key" in error_msg.lower():
            raise AuthorizationError(error_msg)
        raise AuthorizationError(f"API key validation failed: {error_msg}")

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


