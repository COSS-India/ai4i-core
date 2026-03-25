"""
Tenant info resolution from multi-tenant database.

Ported from v1 auth-service main.py get_tenant_info/get_tenant_user_ids
with proper layered architecture (no global DB vars).
"""

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Timeout for multi-tenant DB queries (prevent blocking auth)
_TENANT_QUERY_TIMEOUT = 5.0


class TenantService:
    """
    Resolves tenant information from the multi-tenant database.
    Gracefully degrades if multi-tenant DB is not available.

    Accepts either an AsyncSession or an async_sessionmaker (factory).
    When a factory is provided, sessions are created and closed per query.
    """

    def __init__(self, session_or_factory=None) -> None:
        self._session_or_factory = session_or_factory

    async def _get_session(self):
        """Get a DB session — creates one from factory if needed."""
        if self._session_or_factory is None:
            return None
        if callable(self._session_or_factory):
            return self._session_or_factory()
        return self._session_or_factory

    async def get_tenant_info(
        self, user_id: int, is_tenant: bool
    ) -> Optional[dict[str, Any]]:
        """
        Get tenant information for a user.

        Args:
            user_id: The auth user ID.
            is_tenant: True if user is a tenant admin, False if tenant user.

        Returns:
            Dict with tenant_id, tenant_uuid, schema_name, subscriptions
            or None if not found / DB unavailable.
        """
        db = await self._get_session()
        if db is None:
            return None

        try:
            # Import multi-tenant ORM models (mounted in container)
            from libs.ai4icore_multi_tenant.ai4icore_multi_tenant import Tenant, TenantUser
        except ImportError:
            logger.debug("Multi-tenant library not available.")
            return None

        try:
            if is_tenant:
                # Tenant admin: look up by auth user_id
                stmt = select(Tenant).where(Tenant.user_id == user_id)
                result = await asyncio.wait_for(
                    db.execute(stmt),
                    timeout=_TENANT_QUERY_TIMEOUT,
                )
                tenant = result.scalars().first()
                if tenant:
                    return {
                        "tenant_id": tenant.tenant_id,
                        "tenant_uuid": str(tenant.id),
                        "schema_name": tenant.schema_name,
                        "subscriptions": tenant.subscriptions or [],
                        "user_subscriptions": [],
                    }
            else:
                # Tenant user: join TenantUser with Tenant
                stmt = (
                    select(TenantUser, Tenant)
                    .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                    .where(TenantUser.user_id == user_id)
                )
                result = await asyncio.wait_for(
                    db.execute(stmt),
                    timeout=_TENANT_QUERY_TIMEOUT,
                )
                row = result.first()
                if row:
                    tenant_user, tenant = row
                    return {
                        "tenant_id": tenant.tenant_id,
                        "tenant_uuid": str(tenant.id),
                        "schema_name": tenant.schema_name,
                        "subscriptions": tenant.subscriptions or [],
                        "user_subscriptions": tenant_user.subscriptions or [],
                    }

            return None

        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant info for user %d", user_id)
            return None
        except (ImportError, OSError) as exc:
            logger.warning("Error getting tenant info for user %d: %s", user_id, exc)
            return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def get_tenant_user_ids(self, tenant_id: str) -> Optional[list[int]]:
        """
        Get all user IDs belonging to a tenant (admin + tenant users).
        Returns None if multi-tenant DB is unavailable.
        """
        db = await self._get_session()
        if db is None:
            return None

        try:
            from libs.ai4icore_multi_tenant.ai4icore_multi_tenant import Tenant, TenantUser
        except ImportError:
            return None

        try:
            # Admin users
            admin_q = (
                select(Tenant.user_id.label("user_id"))
                .where(Tenant.tenant_id == tenant_id, Tenant.user_id.is_not(None))
            )
            # Tenant users
            tenant_users_q = (
                select(TenantUser.user_id.label("user_id"))
                .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                .where(Tenant.tenant_id == tenant_id, TenantUser.user_id.is_not(None))
            )
            # Union
            union_q = admin_q.union(tenant_users_q)
            all_users_subq = union_q.subquery("all_tenant_users")
            stmt = select(all_users_subq.c.user_id.distinct())

            result = await asyncio.wait_for(
                db.execute(stmt),
                timeout=_TENANT_QUERY_TIMEOUT,
            )
            rows = result.fetchall()
            return [row[0] for row in rows if row[0] is not None]

        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant user IDs for %s", tenant_id)
            return None
        except (ImportError, OSError) as exc:
            logger.warning("Error getting tenant user IDs for %s: %s", tenant_id, exc)
            return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def resolve_and_cache_tenant_id(
        self, user_id: int, is_tenant: bool
    ) -> Optional[str]:
        """Get tenant_id and return it (for caching on user model)."""
        info = await self.get_tenant_info(user_id, is_tenant)
        return info.get("tenant_id") if info else None
