"""
RBAC Helper for AI4ICore Telemetry Library

Provides RBAC utilities for extracting organization filters from requests.
Follows gateway-trust architecture: when request has been validated by the API gateway
(X-Validated: true, X-User-ID, X-User-Roles), uses those headers. Otherwise falls back
to JWT decode (HS256 only — RS256 tokens are validated at the gateway, not here).
"""
import os
import logging
from typing import Optional, Any, List
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

try:
    from jose import jwt, JWTError
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("python-jose not available, JWT decoding will fail")

# Gateway-injected headers (set by APISIX forward-auth after auth-service validates the token)
GATEWAY_VALIDATED_HEADER = "X-Validated"
GATEWAY_USER_ID_HEADER = "X-User-ID"
GATEWAY_USER_ROLES_HEADER = "X-User-Roles"
GATEWAY_USER_EMAIL_HEADER = "X-User-Email"


def _get_user_from_gateway_headers(request: Request) -> Optional[dict]:
    """
    If the request passed through the gateway with forward-auth, these headers are set.
    Returns dict with user_id, roles, tenant_id (None), email or None if not gateway-validated.
    """
    validated = (request.headers.get(GATEWAY_VALIDATED_HEADER) or "").strip().lower()
    if validated != "true":
        return None
    user_id = (request.headers.get(GATEWAY_USER_ID_HEADER) or "").strip()
    if not user_id:
        return None
    roles_str = request.headers.get(GATEWAY_USER_ROLES_HEADER) or ""
    roles: List[str] = [r.strip() for r in roles_str.split(",") if r.strip()]
    email = (request.headers.get(GATEWAY_USER_EMAIL_HEADER) or "").strip()
    return {"user_id": user_id, "roles": roles, "tenant_id": None, "email": email}


async def get_organization_filter(
    request: Request,
    rbac_enforcer: Any,
    permission: str,
    jwt_secret_key: Optional[str] = None,
    jwt_algorithm: str = "HS256",
    tenant_id_fallback: Optional[Any] = None
) -> Optional[str]:
    """
    Extract tenant_id filter from request based on RBAC.

    Architecture: Prefer gateway-injected headers (X-Validated, X-User-ID, X-User-Roles).
    If present, the gateway has already validated the token; we trust it and use headers.
    Otherwise decode JWT (HS256 only — requests with RS256 tokens should go through the gateway).

    Returns:
        None if user is admin (no filter), tenant_id if normal user

    Raises:
        HTTPException: 401 if no auth, 403 if no permission or no tenant_id (for non-admin users)
    """
    if not JWT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT library not available"
        )

    # 1) Prefer gateway-trust: gateway has already validated the token (RS256 at auth-service)
    gateway_user = _get_user_from_gateway_headers(request)
    if gateway_user:
        user_id = gateway_user["user_id"]
        roles = gateway_user["roles"]
        tenant_id = gateway_user["tenant_id"]  # Gateway does not send tenant_id; use fallback if needed
        logger.debug("Using gateway-injected identity: user_id=%s", user_id)
    else:
        # 2) Fallback: no gateway headers — decode JWT (HS256 only; RS256 tokens must go via gateway)
        secret_key = jwt_secret_key or os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[jwt_algorithm],
                options={"verify_signature": True, "verify_exp": True}
            )
        except JWTError as e:
            logger.warning("JWT verification failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        user_id = payload.get("sub") or payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        roles = payload.get("roles", [])
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in token"
            )

    try:
        if "." not in permission:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid permission format: {permission}"
            )

        resource, action = permission.split(".", 1)
        tenant = "default"

        has_permission = False
        user_sub = f"user:{user_id}"
        if rbac_enforcer.enforce(user_sub, tenant, resource, action):
            has_permission = True
        else:
            for role in roles:
                role_sub = f"role:{role}"
                if rbac_enforcer.enforce(role_sub, tenant, resource, action):
                    has_permission = True
                    break

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )

        is_admin = "ADMIN" in roles or any((r or "").upper() == "ADMIN" for r in roles)

        if is_admin:
            logger.debug("Admin user %s — no tenant filter", user_id)
            return None

        if not tenant_id and tenant_id_fallback:
            try:
                logger.info("User %s has no tenant_id. Attempting database lookup...", user_id)
                if callable(tenant_id_fallback):
                    tenant_id = await tenant_id_fallback(user_id)
                else:
                    tenant_id = None
                if tenant_id:
                    logger.info("Found tenant_id %s for user %s", tenant_id, user_id)
                else:
                    logger.warning("No tenant_id for user %s. Denying access.", user_id)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "message": "Access denied. You must be associated with a tenant to access logs.",
                            "code": "TENANT_REQUIRED",
                            "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                        }
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error querying tenant_id for user %s: %s", user_id, e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": "Access denied. You must be associated with a tenant to access logs.",
                        "code": "TENANT_REQUIRED",
                        "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                    }
                )
        elif not tenant_id:
            logger.warning("User %s has no tenant_id. Denying access.", user_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Access denied. You must be associated with a tenant to access logs.",
                    "code": "TENANT_REQUIRED",
                    "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                }
            )

        logger.debug("User %s tenant_id %s — filtering by tenant", user_id, tenant_id)
        return tenant_id

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in RBAC check: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authorization"
        )


def extract_user_info(request: Request, jwt_secret_key: Optional[str] = None) -> dict:
    """
    Extract user information from request.
    Prefers gateway-injected headers (X-Validated, X-User-ID, X-User-Roles, X-User-Email).
    Otherwise decodes JWT (HS256 only).

    Returns:
        Dict with user_id, tenant_id, roles, email, username
    """
    gateway_user = _get_user_from_gateway_headers(request)
    if gateway_user:
        return {
            "user_id": gateway_user["user_id"],
            "tenant_id": gateway_user["tenant_id"],
            "roles": gateway_user["roles"],
            "email": gateway_user.get("email", ""),
            "username": "",
        }

    if not JWT_AVAILABLE:
        return {}

    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return {}

    token = authorization.split(" ", 1)[1]
    secret_key = jwt_secret_key or os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"verify_signature": True, "verify_exp": True}
        )
        return {
            "user_id": payload.get("sub") or payload.get("user_id"),
            "tenant_id": payload.get("tenant_id"),
            "roles": payload.get("roles", []),
            "email": payload.get("email", ""),
            "username": payload.get("username", ""),
        }
    except Exception:
        return {}
