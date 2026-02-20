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
    """Extract API key from Authorization header.
    
    IMPORTANT: In API_KEY mode, Bearer tokens should NOT be treated as API keys.
    Only extract API key if the header starts with 'ApiKey ' or is a plain API key.
    """
    if not authorization:
        return None
    # Only extract API key if explicitly prefixed with "ApiKey "
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    # If it starts with "Bearer ", it's a JWT token, not an API key
    # Don't extract it as an API key - return None
    if authorization.startswith("Bearer "):
        return None
    # If it's a plain string without prefix, treat it as API key (for backward compatibility)
    return authorization


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()
    service = "language-diarization"
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
            try:
                response = await client.post(validate_url, json=payload)
                response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            except httpx.HTTPStatusError as e:
                # Handle HTTP error responses (4xx, 5xx)
                try:
                    err_json = e.response.json()
                    err_msg = err_json.get("message") or err_json.get("detail") or e.response.text
                except Exception:
                    err_msg = e.response.text or str(e)
                logger.error(f"Auth service returned status {e.response.status_code}: {err_msg}, service={service}, user_id={user_id}")
                raise AuthorizationError(err_msg or "Failed to validate API key permissions")
            
            # Response is 200 OK
            result = response.json()
            # Enforce auth-service 'valid' flag
            if not result.get("valid", False):
                # Preserve detailed message from auth-service, e.g.:
                # "Invalid API key: This key does not have access to language-diarization service"
                error_msg = result.get("message", "Permission denied")
                logger.error(f"Auth-service returned valid=false: {error_msg}, service={service}, user_id={user_id}")
                raise AuthorizationError(error_msg)

            # No need for local ownership check - auth-service already validates this
            # when user_id is provided in BOTH mode
            return result
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
    """Validate JWT access token locally (signature + expiry check).

    Also:
    - Stores the full JWT payload on request.state.jwt_payload
    - Extracts tenant context (schema_name, tenant_id, tenant_uuid) when present

    This mirrors the behavior used by OCR/ASR so that tenant middleware /
    tenant_db_dependency can route to the correct tenant schema.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        logger.info(
            "Language Diarization: decoding JWT token (length=%s, secret_present=%s)",
            len(token),
            bool(JWT_SECRET_KEY),
        )
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_signature": True, "verify_exp": True},
        )
        logger.info(
            "Language Diarization: JWT decode successful. Payload keys: %s",
            list(payload.keys()),
        )

        user_id = payload.get("sub") or payload.get("user_id")
        email = payload.get("email", "")
        username = payload.get("username") or payload.get("email", "")
        roles = payload.get("roles", [])
        token_type = payload.get("type", "")

        if token_type != "access":
            raise AuthenticationError("Invalid token type")
        if not user_id:
            raise AuthenticationError("User ID not found in token")

        request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id
        request.state.api_key_id = None
        request.state.api_key_name = None
        request.state.user_email = email
        request.state.is_authenticated = True
        # Store JWT payload so tenant_context resolver can use it
        request.state.jwt_payload = payload

        # Extract tenant schema directly from JWT if available
        schema_name = payload.get("schema_name")
        if schema_name:
            request.state.tenant_schema = schema_name
            request.state.tenant_id = payload.get("tenant_id")
            request.state.tenant_uuid = payload.get("tenant_uuid")
            logger.info(
                "Language Diarization: extracted tenant context from JWT - "
                "tenant_id=%s schema_name=%s",
                payload.get("tenant_id"),
                schema_name,
            )
        else:
            logger.info(
                "Language Diarization: JWT payload does not contain schema_name. "
                "Available keys: %s",
                list(payload.keys()),
            )

        return {
            "user_id": int(user_id) if isinstance(user_id, (str, int)) else user_id,
            "api_key_id": None,
            "user": {"username": username, "email": email, "roles": roles},
            "api_key": None,
        }

    except JWTError as e:
        logger.warning("Language Diarization: JWT verification failed: %s", e)
        if "expired" in str(e).lower() or "exp" in str(e).lower():
            raise AuthenticationError("Invalid or expired token")
        raise AuthenticationError("Invalid or expired token")
    except Exception as e:
        logger.error("Language Diarization: unexpected error during JWT verification: %s", e)
        raise AuthenticationError("Failed to verify token")


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_auth_source: str = Header(default="API_KEY", alias="X-Auth-Source"),
) -> Dict[str, Any]:
    """Authentication provider dependency with permission checks."""
    auth_source = (x_auth_source or "API_KEY").upper()

    # AUTH_TOKEN mode is not allowed for this service – API key is always required
    if auth_source == "AUTH_TOKEN":
        raise AuthenticationError("Missing API key")

    # BOTH mode - require both JWT and API key
    api_key = x_api_key or get_api_key_from_header(authorization)
    if auth_source == "BOTH":
        try:
            # 1) Authenticate user via JWT
            bearer_result = await authenticate_bearer_token(request, authorization)
            jwt_user_id = bearer_result.get("user_id")

            if not api_key:
                raise AuthenticationError("Missing API key")

            # 2) Validate API key + permissions via auth-service (single source of truth),
            # passing jwt_user_id so auth-service can enforce ownership.
            service, action = determine_service_and_action(request)
            auth_result = await validate_api_key_permissions(api_key, service, action, user_id=jwt_user_id)
            
            # CRITICAL: Always check valid field - auth-service may return valid=false
            if not auth_result.get("valid", False):
                error_msg = auth_result.get("message", "API key does not belong to the authenticated user")
                api_key_user_id = auth_result.get("user_id")
                logger.error(f"Auth-service returned valid=false in BOTH mode: {error_msg}, jwt_user_id={jwt_user_id}, api_key_user_id={api_key_user_id}")
                
                # In BOTH mode, if we provided user_id and auth-service returned valid=false,
                # we need to distinguish between ownership and permission.
                # When user_id is provided, auth-service checks ownership, but it may return
                # a permission error if the API key doesn't have permission (even if it doesn't belong to the user).
                # So we need to check: if user_ids don't match OR if there's no user_id in response, it's ownership.
                if jwt_user_id is not None:
                    # Check if auth-service returned a user_id that matches our requested user_id
                    ownership_issue = True
                    if api_key_user_id is not None:
                        try:
                            api_key_user_id_int = int(api_key_user_id)
                            requested_user_id_int = int(jwt_user_id)
                            if api_key_user_id_int == requested_user_id_int:
                                # User IDs match - check if error message indicates ownership
                                error_msg_lower = error_msg.lower()
                                if "does not belong" in error_msg_lower or "ownership" in error_msg_lower:
                                    # Error explicitly indicates ownership
                                    logger.error(f"BOTH mode: valid=false, user_id matches ({jwt_user_id}), but error indicates ownership: {error_msg}")
                                else:
                                    # User IDs match and error doesn't indicate ownership: permission issue
                                    ownership_issue = False
                                    logger.error(f"BOTH mode: valid=false but user_id matches ({jwt_user_id}) and error indicates permission, treating as permission issue: {error_msg}")
                            else:
                                # Ownership mismatch: API key belongs to a different user
                                logger.error(f"API key ownership mismatch: requested_user_id={requested_user_id_int}, api_key_user_id={api_key_user_id_int}")
                        except (TypeError, ValueError):
                            # If conversion fails, cannot confirm it's permission issue, treat as ownership
                            logger.error(f"BOTH mode: valid=false with user_id={jwt_user_id} provided, but user_id conversion failed, treating as ownership issue")
                    else:
                        # No user_id in response but we provided one: this means ownership issue
                        logger.error(f"BOTH mode: valid=false with user_id={jwt_user_id} provided, but no user_id in response - treating as ownership issue")
                    
                    if ownership_issue:
                        # Ownership issue: API key doesn't belong to the authenticated user
                        raise AuthenticationError("API key does not belong to the authenticated user")
                    else:
                        # Permission issue: preserve the original error message
                        raise AuthenticationError(error_msg)
                
                # For other errors (when user_id not provided), preserve the message
                raise AuthenticationError(error_msg)

            # 3) Populate request.state – keep JWT as primary identity (matching ASR/TTS/NMT)
            request.state.user_id = jwt_user_id
            request.state.api_key_id = None
            request.state.api_key_name = None
            request.state.user_email = bearer_result.get("user", {}).get("email")
            request.state.is_authenticated = True

            return bearer_result
        except (AuthenticationError, AuthorizationError, InvalidAPIKeyError, ExpiredAPIKeyError) as e:
            # For ANY auth/key error in BOTH mode, surface the underlying message when available
            logger.error(f"Language-diarization BOTH mode: Authentication/Authorization error: {e}")
            raise AuthenticationError(str(e) or "API key does not belong to the authenticated user")
        except Exception as e:
            logger.error(f"Language-diarization BOTH mode: Unexpected error: {e}", exc_info=True)
            raise AuthenticationError("API key does not belong to the authenticated user")

    # API_KEY mode (default) - require API key only
    # IMPORTANT: In API_KEY mode, if Authorization header contains "Bearer " token,
    # it should be rejected (not treated as API key) unless X-API-Key header is provided
    if authorization and authorization.startswith("Bearer "):
        # In API_KEY mode, Bearer tokens are not accepted
        # User must provide X-API-Key header instead
        if not api_key:
            raise AuthenticationError(
                "API key required. Bearer tokens are not accepted in API_KEY mode. "
                "Please provide X-API-Key header or set X-Auth-Source to AUTH_TOKEN."
            )
    
    if not api_key:
        raise AuthenticationError("Missing API key")

    service, action = determine_service_and_action(request)
    await validate_api_key_permissions(api_key, service, action)

    # Store API key info in request.state
    request.state.user_id = None
    request.state.api_key_id = None  # TODO: Get from auth service response
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

