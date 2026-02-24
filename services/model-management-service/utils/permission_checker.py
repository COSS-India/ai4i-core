"""
Permission checking utility for RBAC
Queries role_permissions table to check if user has required permission
"""
from fastapi import HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from db_connection import get_auth_db_session
from models.auth_models import Role, Permission, RolePermission, UserRole
from logger import logger


async def check_user_permission(
    user_id: Optional[int],
    user_roles: Optional[List[str]],
    permission_name: str,
    db: AsyncSession
) -> bool:
    """
    Check if user has the required permission by querying role_permissions table.
    
    Args:
        user_id: User ID (optional, for direct user-role check)
        user_roles: List of role names from JWT token (e.g., ['ADMIN', 'MODERATOR'])
        permission_name: Permission name in format 'resource.action' (e.g., 'model.create')
        db: Database session
        
    Returns:
        True if user has permission, False otherwise
    """
    if not permission_name or "." not in permission_name:
        logger.warning(f"Invalid permission format: {permission_name}")
        return False
    
    # Split permission into resource and action
    resource, action = permission_name.split(".", 1)
    
    # If we have user_roles from JWT token, check those roles
    if user_roles:
        role_names = [role.upper() for role in user_roles if role]
        
        # Query: Check if any of the user's roles has the required permission
        result = await db.execute(
            select(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .where(
                Role.name.in_(role_names),
                Permission.resource == resource,
                Permission.action == action
            )
        )
        permission_found = result.scalar_one_or_none()
        
        if permission_found:
            logger.debug(f"User with roles {role_names} has permission {permission_name}")
            return True
    
    # If we have user_id, check user's roles from database
    if user_id:
        result = await db.execute(
            select(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Permission.resource == resource,
                Permission.action == action
            )
        )
        permission_found = result.scalar_one_or_none()
        
        if permission_found:
            logger.debug(f"User {user_id} has permission {permission_name}")
            return True
    
    logger.debug(f"User (id={user_id}, roles={user_roles}) does NOT have permission {permission_name}")
    return False


def require_permission_dependency(permission: str):
    """
    Create a dependency function that checks permission before body validation.
    This ensures permission check happens before FastAPI validates the request body.
    """
    async def _check_permission(
        request: Request,
        db: AsyncSession = Depends(get_auth_db_session)
    ) -> None:
        await require_permission(permission, request, db)
    
    return _check_permission


async def require_permission(
    permission: str,
    request: Request,
    db: AsyncSession
) -> None:
    """
    Check if user has required permission, raise HTTPException if not.
    
    Args:
        permission: Permission name (e.g., 'model.create')
        request: FastAPI request object
        db: Database session
        
    Raises:
        HTTPException: 403 if permission is missing, 401 if not authenticated
    """
    # Allow anonymous access for try-it requests (X-Try-It header)
    # This enables read-only model/service usage for anonymous "try-it" flows
    try_it_header = request.headers.get("X-Try-It") or request.headers.get("x-try-it")
    if try_it_header and str(try_it_header).strip().lower() == "true":
        # Skip auth/permission checks for try-it flows
        return
    
    # Get user info from request state (set by AuthProvider)
    user_id = getattr(request.state, 'user_id', None)
    is_authenticated = getattr(request.state, 'is_authenticated', False)
    
    if not is_authenticated:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHORIZED",
                "message": "Authentication required"
            }
        )
    
    # Get roles from request state (set by AuthProvider when using Bearer token)
    # For API key auth, user_id will be available but roles might not be in request.state.user
    user_info = getattr(request.state, 'user', None)
    user_roles = []
    if user_info:
        if isinstance(user_info, dict):
            user_roles = user_info.get('roles', [])
        elif hasattr(user_info, 'roles'):
            user_roles = user_info.roles if isinstance(user_info.roles, list) else []
    
    # If no roles from token but we have user_id, query from database for error message
    if not user_roles and user_id:
        result = await db.execute(
            select(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        user_roles = [row[0] for row in result.all()]
    
    # Check permission (will query database for user roles if user_roles is empty but user_id is available)
    has_permission = await check_user_permission(
        user_id=user_id,
        user_roles=user_roles,
        permission_name=permission,
        db=db
    )
    
    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "PERMISSION_DENIED",
                "message": "Only ADMIN or MODERATOR roles can perform this operation."
            }
        )
