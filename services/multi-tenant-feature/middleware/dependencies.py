from fastapi import HTTPException,status,Request,Depends
from middleware.auth_provider import AuthProvider
from logger import logger
from services.tenant_service import _get_roles_from_auth
from jose import jwt, JWTError
import os
from ai4icore_env import app_env

JWT_SECRET_KEY = app_env.jwt_secret_key
JWT_ALGORITHM = app_env.jwt_algorithm


async def require_admin(request: Request,_=Depends(AuthProvider)):
    """
    Dependency that ensures the caller has ADMIN role in the auth service.
    Uses the authenticated user_id from AuthProvider and resolves roles via auth.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    roles = []

    # 1) Try to read roles directly from JWT claims if we can decode locally
    if token and JWT_SECRET_KEY:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            token_roles = payload.get("roles") or []
            if isinstance(token_roles, str):
                roles = [token_roles]
            elif isinstance(token_roles, list):
                roles = [str(r).strip() for r in token_roles if str(r).strip()]
        except JWTError:
            # Fall back to auth-service lookup on any JWT decode error
            roles = []

    # 2) If roles still empty, fall back to auth service
    if not roles:
        roles = await _get_roles_from_auth(user_id=user_id, auth_header=auth_header)

    # Expose roles on request.state for downstream handlers/services
    request.state.roles = roles if roles else None

    # Treat any role equal (case-insensitive) to ADMIN as admin
    is_admin = any(str(r).upper() == "ADMIN" for r in roles)

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required to perform the action",
        )

    return


async def require_tenant_admin(request: Request,_=Depends(AuthProvider)):
    """
    Dependency that ensures the caller has either ADMIN or TENANT ADMIN role in the auth service.
    Uses the authenticated user_id from AuthProvider and resolves roles via auth.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    roles = []

    # 1) Try to read roles directly from JWT claims if we can decode locally
    if token and JWT_SECRET_KEY:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            token_roles = payload.get("roles") or []
            if isinstance(token_roles, str):
                roles = [token_roles]
            elif isinstance(token_roles, list):
                roles = [str(r).strip() for r in token_roles if str(r).strip()]
        except JWTError:
            # Fall back to auth-service lookup on any JWT decode error
            roles = []

    # 2) If roles still empty, fall back to auth service
    if not roles:
        roles = await _get_roles_from_auth(user_id=user_id, auth_header=auth_header)

    # Expose roles on request.state for downstream handlers/services
    request.state.roles = roles if roles else None

    # Treat any role equal (case-insensitive) to ADMIN as admin
    is_tenant_admin = any(str(r).upper() == "TENANT ADMIN" for r in roles)
    is_admin = any(str(r).upper() == "ADMIN" for r in roles)

    if not (is_admin or is_tenant_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to perform the action",
        )

    return