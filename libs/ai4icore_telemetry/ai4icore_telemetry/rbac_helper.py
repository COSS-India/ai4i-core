"""
RBAC Helper for AI4ICore Telemetry Library

Provides RBAC utilities for extracting organization filters from requests.
"""
import os
import logging
from typing import Optional, Any
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

try:
    from jose import jwt, JWTError
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("python-jose not available, JWT decoding will fail")


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
    
    This function:
    1. Extracts JWT token from request
    2. Decodes JWT to get user_id, tenant_id, and roles
    3. Checks Casbin permissions
    4. Returns tenant_id filter (None for admin, tenant_id for users)
    
    Args:
        request: FastAPI request object
        rbac_enforcer: Casbin enforcer instance
        permission: Permission to check (e.g., "logs.read", "traces.read")
        jwt_secret_key: JWT secret key (defaults to JWT_SECRET_KEY env var)
        jwt_algorithm: JWT algorithm (default: HS256)
    
    Returns:
        None if user is admin (no filter), tenant_id if normal user
    
    Raises:
        HTTPException: 401 if no token, 403 if no permission or no tenant_id (for non-admin users)
    """
    if not JWT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT library not available"
        )
    
    # Get JWT secret key
    secret_key = jwt_secret_key or os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    
    # Extract JWT token from Authorization header
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.split(" ", 1)[1]
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[jwt_algorithm],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        # Extract user info
        user_id = payload.get("sub") or payload.get("user_id")
        tenant_id = payload.get("tenant_id")
        roles = payload.get("roles", [])
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID not found in token"
            )
        
        # Check permission using Casbin
        # Permission format: "logs.read" or "traces.read"
        # We need to split into resource and action
        if "." not in permission:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid permission format: {permission}"
            )
        
        resource, action = permission.split(".", 1)
        tenant = "default"  # Casbin domain/tenant
        
        # Check if user has permission
        has_permission = False
        
        # Check by user ID
        user_sub = f"user:{user_id}"
        if rbac_enforcer.enforce(user_sub, tenant, resource, action):
            has_permission = True
        else:
            # Check by roles
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
        
        # Determine tenant_id filter based on role
        # ADMIN role can see all (no filter)
        # Other roles see only their tenant's logs
        is_admin = "ADMIN" in roles or any(role.upper() == "ADMIN" for role in roles)
        
        if is_admin:
            # Admin sees all - no tenant_id filter
            logger.debug(f"Admin user {user_id} - returning None (no filter, sees all logs)")
            return None
        else:
            # Normal user - must have tenant_id to filter by their tenant
            if not tenant_id:
                # Try fallback: query database for tenant_id if callback provided
                if tenant_id_fallback:
                    try:
                        logger.info(f"User {user_id} has no tenant_id in token. Attempting database lookup...")
                        # Call the fallback function (should be async)
                        if callable(tenant_id_fallback):
                            tenant_id = await tenant_id_fallback(user_id)
                        else:
                            tenant_id = None
                        
                        if tenant_id:
                            logger.info(f"Found tenant_id {tenant_id} for user {user_id} from database")
                        else:
                            logger.warning(f"User {user_id} has no tenant_id in token or database. Denying access.")
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail={
                                    "message": "Access denied. You must be registered to a tenant to view logs.",
                                    "code": "TENANT_REQUIRED",
                                    "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                                }
                            )
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(f"Error querying tenant_id from database for user {user_id}: {e}", exc_info=True)
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail={
                                "message": "Access denied. You must be registered to a tenant to view logs.",
                                "code": "TENANT_REQUIRED",
                                "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                            }
                        )
                else:
                    logger.warning(f"User {user_id} has no tenant_id in token. Denying access.")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "message": "Access denied. You must be registered to a tenant to view logs.",
                            "code": "TENANT_REQUIRED",
                            "hint": "Please register to a tenant to access logs and traces. If you recently registered, please log out and log back in to refresh your token."
                        }
                    )
            logger.debug(f"User {user_id} with tenant_id {tenant_id} - filtering by tenant")
            return tenant_id
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in RBAC check: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authorization"
        )


def extract_user_info(request: Request, jwt_secret_key: Optional[str] = None) -> dict:
    """
    Extract user information from JWT token (helper function).
    
    Args:
        request: FastAPI request object
        jwt_secret_key: JWT secret key (defaults to JWT_SECRET_KEY env var)
    
    Returns:
        Dict with user_id, tenant_id, roles, email, username
    """
    if not JWT_AVAILABLE:
        return {}
    
    secret_key = jwt_secret_key or os.getenv("JWT_SECRET_KEY", "dhruva-jwt-secret-key-2024-super-secure")
    
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return {}
    
    token = authorization.split(" ", 1)[1]
    
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
            "username": payload.get("username", "")
        }
    except Exception:
        return {}

