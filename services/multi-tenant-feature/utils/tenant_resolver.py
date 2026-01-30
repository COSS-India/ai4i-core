"""
Tenant Context Resolver
Resolves tenant information from user_id or JWT token
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

async def resolve_tenant_from_user_id(
    user_id: int,
    tenant_db: AsyncSession,
    auth_db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Resolve tenant context from user_id.
    Returns tenant_id, tenant_uuid, schema_name, subscriptions
    """
    try:
        from models.db_models import Tenant, TenantUser 
        from models.auth_models import UserDB
        from models.enum_tenant import TenantStatus
        
        # Get user from auth DB
        user = await auth_db.get(UserDB, user_id)
        if not user:
            logger.warning(f"User {user_id} not found in auth DB")
            return None
        
        tenant_user = None
        if user.is_tenant:
            stmt = select(Tenant).where(Tenant.user_id == user.id)
            tenant = await tenant_db.scalar(stmt)
            if not tenant:
                logger.warning(f"Tenant not found for user_id {user_id}")
                return None
        else:
            stmt = select(TenantUser).where(TenantUser.user_id == user.id)
            tenant_user = await tenant_db.scalar(stmt)
        
            if not tenant_user:
                logger.warning(f"Tenant user record not found for user_id {user_id}")
                return None
        
            tenant = await tenant_db.get(Tenant, tenant_user.tenant_uuid)
            if not tenant:
                logger.warning(f"Tenant not found for tenant_uuid {tenant_user.tenant_uuid}")
                return None
            
        if tenant.status != TenantStatus.ACTIVE:
            logger.warning(f"Tenant {tenant.tenant_id} is not ACTIVE (status: {tenant.status})")
            return None
        
        return {
            "tenant_id": tenant.tenant_id,
            "tenant_uuid": str(tenant.id),
            "schema_name": tenant.schema_name,
            "subscriptions": tenant.subscriptions,
            "user_subscriptions": tenant_user.subscriptions if tenant_user else [],
            "status": tenant.status.value
        }
    except Exception as e:
        logger.error(f"Error resolving tenant from user_id {user_id}: {e}", exc_info=True)
        return None

async def resolve_tenant_from_jwt(jwt_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract tenant context from JWT payload.
    """
    tenant_id = jwt_payload.get("tenant_id")
    if not tenant_id:
        return None
    
    return {
        "tenant_id": tenant_id,
        "tenant_uuid": jwt_payload.get("tenant_uuid"),
        "schema_name": jwt_payload.get("schema_name"),
        "subscriptions": jwt_payload.get("subscriptions", []),
        "user_subscriptions": jwt_payload.get("user_subscriptions", []),
    }
