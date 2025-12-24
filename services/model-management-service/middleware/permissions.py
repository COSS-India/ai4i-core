"""
Permission checker for role-based access control.
Provides dependencies for protecting endpoints that require specific roles.
"""
from fastapi import Request, Depends, HTTPException, status
from middleware.auth_provider import AuthProvider
from logger import logger


class PermissionChecker:
    """Permission checker for role-based access control."""
    
    @staticmethod
    async def has_moderator_access(request: Request, auth_context: dict = Depends(AuthProvider)) -> dict:
        """
        Check if the user has Moderator role access.
        Returns auth context if authorized, raises HTTPException if not.
        """
        user = auth_context.get("user")
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        # Extract roles from user object
        # Handle both dict and object formats
        if isinstance(user, dict):
            roles = user.get("roles", [])
        else:
            roles = getattr(user, "roles", [])
        
        # Check if user has Moderator role
        if not roles or "Moderator" not in roles:
            logger.warning(f"User {auth_context.get('user_id')} attempted to access Moderator-only endpoint")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Moderator role required for this operation"
            )
        
        return auth_context


# Dependency for Moderator role requirement
ModeratorRequired = Depends(PermissionChecker.has_moderator_access)

