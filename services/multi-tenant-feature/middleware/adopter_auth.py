"""
Authentication dependency for Adopter Admin access.
Adopter Admin is a user who owns a tenant (has tenant with user_id matching their user_id).
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any

from middleware.auth_provider import AuthProvider
from db_connection import get_tenant_db_session
from models.db_models import Tenant
from logger import logger


async def require_adopter_admin(
    request: Request,
    auth_context: Dict[str, Any] = Depends(AuthProvider),
    db: AsyncSession = Depends(get_tenant_db_session),
) -> Dict[str, Any]:
    """
    Dependency to ensure the current user is an adopter admin.
    An adopter admin is a user who owns at least one tenant (tenant.user_id == user.id).
    
    Returns:
        Dict containing auth context with user_id and user info
    Raises:
        HTTPException 403 if user is not an adopter admin
    """
    user_id = auth_context.get("user_id")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Check if user is an adopter admin (owns at least one tenant)
    result = await db.execute(
        select(Tenant).where(Tenant.user_id == user_id).limit(1)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only adopter admins can access this endpoint. You must own at least one tenant."
        )
    
    logger.info(f"Adopter admin access granted for user_id={user_id}")
    return auth_context
