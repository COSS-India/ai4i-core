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


def get_organization_filter(
    request: Request,
    rbac_enforcer: Any,
    permission: str,
    jwt_secret_key: Optional[str] = None,
    jwt_algorithm: str = "HS256"
) -> Optional[str]:
    """
    Extract organization filter from request based on RBAC.
    
    This function:
    1. Extracts JWT token from request
    2. Decodes JWT to get user_id, tenant_id, and roles
    3. Checks Casbin permissions
    4. Returns organization filter (None for admin, tenant_id for users)
    
    Args:
        request: FastAPI request object
        rbac_enforcer: Casbin enforcer instance
        permission: Permission to check (e.g., "logs.read", "traces.read")
        jwt_secret_key: JWT secret key (defaults to JWT_SECRET_KEY env var)
        jwt_algorithm: JWT algorithm (default: HS256)
    
    Returns:
        None if user is admin (no filter), tenant_id if normal user, or raises HTTPException
    
    Raises:
        HTTPException: 401 if no token, 403 if no permission
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
        
        # Determine organization filter based on role
        # ADMIN role can see all (no filter)
        # Other roles see only their organization
        is_admin = "ADMIN" in roles or any(role.upper() == "ADMIN" for role in roles)
        
        if is_admin:
            # Admin sees all - no organization filter
            return None
        else:
            # Normal user - filter by their organization
            if not tenant_id:
                logger.warning(f"User {user_id} has no tenant_id in token. Allowing access without organization filter (for testing).")
                # For testing: if tenant_id is missing, allow access but return None (no filter)
                # In production, you may want to deny access or use a default organization
                # TODO: In production, either:
                #   1. Ensure all tokens include tenant_id
                #   2. Deny access: raise HTTPException(status_code=403, detail="Organization not found in token")
                #   3. Use a default organization: return "default_org_id"
                return None  # No filter - see all logs (for testing only)
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

