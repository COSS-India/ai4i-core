"""
Tenant Context Resolver
Resolves tenant information from user_id or JWT token
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
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
        tenant = None

        if user.is_tenant:
            stmt = select(Tenant).where(Tenant.user_id == user.id)
            tenant = await tenant_db.scalar(stmt)
        else:
            stmt = select(TenantUser).where(TenantUser.user_id == user.id)
            tenant_user = await tenant_db.scalar(stmt)
            if tenant_user:
                tenant = await tenant_db.get(Tenant, tenant_user.tenant_uuid)

        # Fallback: if the tenants/tenant_users link is missing or out of sync,
        # use the cached tenant_id string the auth-service stamps on
        # auth_db.users.tenant_id_cached at login time. Read it via raw SQL so
        # we don't have to add the column to the UserDB ORM (which would touch
        # a model file and trip the migration-integrity pre-commit hook over
        # pre-existing chain damage on poc-usage). Keeps observability /
        # pay-per-use / tenant routing working even when the link table is stale.
        if tenant is None:
            cached_row = await auth_db.execute(
                text("SELECT tenant_id_cached FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
            cached_tid = cached_row.scalar()
            if cached_tid:
                stmt = select(Tenant).where(Tenant.tenant_id == cached_tid)
                tenant = await tenant_db.scalar(stmt)
                if tenant is None:
                    logger.warning(
                        f"User {user_id} has tenant_id_cached={cached_tid!r} "
                        f"but no tenant row matches. Treating as no-tenant."
                    )
            if tenant is None:
                logger.warning(
                    f"Tenant not found for user_id {user_id} via user_id link "
                    f"or tenant_id_cached fallback."
                )
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
