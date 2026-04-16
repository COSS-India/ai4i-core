"""
Tenant user resolution from multi-tenant database.

Used only by the admin session-revocation endpoint to look up
which auth user IDs belong to a given tenant.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_TENANT_QUERY_TIMEOUT = 5.0

try:
    from ai4icore_multi_tenant import Tenant, TenantUser
except ImportError:
    try:
        from libs.ai4icore_multi_tenant.ai4icore_multi_tenant import Tenant, TenantUser
    except ImportError:
        Tenant = None
        TenantUser = None


class TenantService:
    """Resolves tenant user IDs from the multi-tenant database."""

    def __init__(self, session_or_factory=None, cache_service: CacheService | None = None) -> None:
        self._session_or_factory = session_or_factory
        self._cache_service = cache_service

    async def _get_session(self) -> Optional[AsyncSession]:
        if self._session_or_factory is None:
            return None
        if callable(self._session_or_factory):
            return self._session_or_factory()
        return self._session_or_factory

    async def get_tenant_user_ids(self, tenant_id: str) -> Optional[list[int]]:
        """Get all auth user IDs belonging to a tenant (admin + tenant users)."""
        if Tenant is None or TenantUser is None:
            logger.debug("Multi-tenant library not available.")
            return None

        db = await self._get_session()
        if db is None:
            return None

        try:
            admin_q = (
                select(Tenant.user_id.label("user_id"))
                .where(Tenant.tenant_id == tenant_id, Tenant.user_id.is_not(None))
            )
            tenant_users_q = (
                select(TenantUser.user_id.label("user_id"))
                .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                .where(Tenant.tenant_id == tenant_id, TenantUser.user_id.is_not(None))
            )
            union_q = admin_q.union(tenant_users_q)
            all_users_subq = union_q.subquery("all_tenant_users")
            stmt = select(all_users_subq.c.user_id.distinct())

            result = await asyncio.wait_for(db.execute(stmt), timeout=_TENANT_QUERY_TIMEOUT)
            return [row[0] for row in result.fetchall() if row[0] is not None]

        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant user IDs for %s", tenant_id)
            return None
        except (ImportError, OSError) as exc:
            logger.warning("Error getting tenant user IDs for %s: %s", tenant_id, exc)
            return None
        finally:
            if callable(self._session_or_factory):
                await db.close()
