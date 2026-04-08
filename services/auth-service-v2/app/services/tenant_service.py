"""
Tenant info resolution from multi-tenant database.

Ported from v1 auth-service main.py get_tenant_info/get_tenant_user_ids
with proper layered architecture (no global DB vars).
"""

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
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
            logger.debug("TenantService multi-tenant session factory not configured.")
            return None
        if callable(self._session_or_factory):
            logger.debug("TenantService creating multi-tenant AsyncSession from factory.")
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
            # Import multi-tenant ORM models.
            # Package name is `ai4icore_multi_tenant` (not `libs.ai4icore_multi_tenant`).
            from ai4icore_multi_tenant import Tenant, TenantUser
        except ImportError:
            # Backward-compatibility fallback (if libs/ is on PYTHONPATH).
            try:
                from libs.ai4icore_multi_tenant.ai4icore_multi_tenant import Tenant, TenantUser
            except ImportError:
                logger.debug("Multi-tenant library not available (neither ai4icore_multi_tenant nor libs.ai4icore_multi_tenant).")
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
        except (ImportError, OSError, SQLAlchemyError) as exc:
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
            from ai4icore_multi_tenant import Tenant, TenantUser
        except ImportError:
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
        except (ImportError, OSError, SQLAlchemyError) as exc:
            logger.warning("Error getting tenant user IDs for %s: %s", tenant_id, exc)
            return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def resolve_and_cache_tenant_id(
        self, user_id: int, is_tenant: bool
    ) -> Optional[str]:
        """Get tenant_id and return it (for caching on user model)."""
        logger.debug("Resolving tenant_id via multi-tenant DB (user_id=%s is_tenant=%s)", user_id, is_tenant)
        info = await self.get_tenant_info(user_id, is_tenant)
        return info.get("tenant_id") if info else None

    def _normalize_status(self, status_val: Any) -> Optional[str]:
        if status_val is None:
            return None
        # SQLAlchemy Enum(BlaEnum) often returns the Enum instance; also allow raw strings.
        status = str(getattr(status_val, "value", status_val)).strip().upper()
        if "." in status:
            status = status.split(".")[-1]
        return status

    async def get_tenant_status(self, tenant_id: str) -> Optional[str]:
        """
        Returns the Tenant.status for the given tenant_id.
        Uses ORM queries against the multi-tenant DB (no raw SQL / no HTTP).
        """
        db = await self._get_session()
        if db is None:
            logger.warning("Multi-tenant DB not connected; tenant status lookup disabled (tenant_id=%s)", tenant_id)
            return None

        try:
            from ai4icore_multi_tenant import Tenant

            tenant_id_norm = (tenant_id or "").strip().lower()
            stmt = (
                select(Tenant.status)
                .where(func.lower(func.trim(Tenant.tenant_id)) == tenant_id_norm)
                .limit(1)
            )
            result = await asyncio.wait_for(
                db.execute(stmt),
                timeout=_TENANT_QUERY_TIMEOUT,
            )
            status = self._normalize_status(result.scalar_one_or_none())
            if status is None:
                logger.debug("Tenant status not found in multi-tenant DB (tenant_id=%s)", tenant_id)
            else:
                logger.debug("Tenant status resolved (tenant_id=%s status=%s)", tenant_id, status)
            return status

        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant status for tenant_id=%s", tenant_id)
            return None
        except SQLAlchemyError as exc:
            logger.warning(
                "Multi-tenant DB error getting tenant status (tenant_id=%s): %s",
                tenant_id,
                exc,
            )
            return None
        except ImportError:
            try:
                from libs.ai4icore_multi_tenant.ai4icore_multi_tenant.models import Tenant

                tenant_id_norm = (tenant_id or "").strip().lower()
                stmt = (
                    select(Tenant.status)
                    .where(func.lower(func.trim(Tenant.tenant_id)) == tenant_id_norm)
                    .limit(1)
                )
                result = await asyncio.wait_for(
                    db.execute(stmt), timeout=_TENANT_QUERY_TIMEOUT
                )
                status = self._normalize_status(result.scalar_one_or_none())
                return status
            except ImportError:
                logger.debug("Multi-tenant library not available.")
                return None
            except asyncio.TimeoutError:
                logger.warning("Timeout getting tenant status (fallback path) tenant_id=%s", tenant_id)
                return None
            except SQLAlchemyError as exc:
                logger.warning(
                    "Multi-tenant DB error getting tenant status (fallback path, tenant_id=%s): %s",
                    tenant_id,
                    exc,
                )
                return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def get_tenant_user_status(self, tenant_id: str, user_id: int) -> Optional[str]:
        """
        Returns the TenantUser.status for (tenant_id, user_id).
        """
        db = await self._get_session()
        if db is None:
            logger.warning(
                "Multi-tenant DB not connected; tenant-user status lookup disabled (tenant_id=%s user_id=%s)",
                tenant_id,
                user_id,
            )
            return None

        try:
            from ai4icore_multi_tenant import TenantUser

            tenant_id_norm = (tenant_id or "").strip().lower()
            stmt = (
                select(TenantUser.status)
                .where(
                    func.lower(func.trim(TenantUser.tenant_id)) == tenant_id_norm,
                    TenantUser.user_id == user_id,
                )
                .limit(1)
            )
            result = await asyncio.wait_for(
                db.execute(stmt),
                timeout=_TENANT_QUERY_TIMEOUT,
            )
            status = self._normalize_status(result.scalar_one_or_none())
            if status is None:
                logger.debug(
                    "Tenant user status not found in multi-tenant DB (tenant_id=%s user_id=%s)",
                    tenant_id,
                    user_id,
                )
            else:
                logger.debug(
                    "Tenant user status resolved (tenant_id=%s user_id=%s status=%s)",
                    tenant_id,
                    user_id,
                    status,
                )
            return status

        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant user status for tenant_id=%s user_id=%s", tenant_id, user_id)
            return None
        except SQLAlchemyError as exc:
            logger.warning(
                "Multi-tenant DB error getting tenant user status (tenant_id=%s user_id=%s): %s",
                tenant_id,
                user_id,
                exc,
            )
            return None
        except ImportError:
            try:
                from libs.ai4icore_multi_tenant.ai4icore_multi_tenant.models import TenantUser

                tenant_id_norm = (tenant_id or "").strip().lower()
                stmt = (
                    select(TenantUser.status)
                    .where(
                        func.lower(func.trim(TenantUser.tenant_id)) == tenant_id_norm,
                        TenantUser.user_id == user_id,
                    )
                    .limit(1)
                )
                result = await asyncio.wait_for(
                    db.execute(stmt), timeout=_TENANT_QUERY_TIMEOUT
                )
                status = self._normalize_status(result.scalar_one_or_none())
                return status
            except ImportError:
                logger.debug("Multi-tenant library not available.")
                return None
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout getting tenant user status (fallback path) tenant_id=%s user_id=%s",
                    tenant_id,
                    user_id,
                )
                return None
            except SQLAlchemyError as exc:
                logger.warning(
                    "Multi-tenant DB error getting tenant user status (fallback path, tenant_id=%s user_id=%s): %s",
                    tenant_id,
                    user_id,
                    exc,
                )
                return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def get_tenant_status_by_user_id(
        self, user_id: int, is_tenant: bool
    ) -> Optional[str]:
        """
        Fallback: resolve Tenant.status directly using auth user_id.
        This avoids reliance on potentially-stale/bad tenant_id values.
        """
        db = await self._get_session()
        if db is None:
            return None

        try:
            from ai4icore_multi_tenant import Tenant, TenantUser

            if is_tenant:
                # First attempt: tenant admin mapped on Tenant.user_id.
                stmt_admin = select(Tenant.status).where(Tenant.user_id == user_id).limit(1)
                result = await asyncio.wait_for(
                    db.execute(stmt_admin),
                    timeout=_TENANT_QUERY_TIMEOUT,
                )
                status = self._normalize_status(result.scalar_one_or_none())
                if status is not None:
                    return status

                # Second attempt: some schemas store tenant admins as tenant-user rows too.
                stmt_admin_via_tenant_user = (
                    select(Tenant.status)
                    .select_from(TenantUser)
                    .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                    .where(TenantUser.user_id == user_id)
                    .limit(1)
                )
                result = await asyncio.wait_for(
                    db.execute(stmt_admin_via_tenant_user),
                    timeout=_TENANT_QUERY_TIMEOUT,
                )
                return self._normalize_status(result.scalar_one_or_none())

            # Tenant user: join via tenant_uuid to avoid tenant_id string mismatches.
            stmt_user = (
                select(Tenant.status)
                .select_from(TenantUser)
                .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                .where(TenantUser.user_id == user_id)
                .limit(1)
            )
            result = await asyncio.wait_for(
                db.execute(stmt_user),
                timeout=_TENANT_QUERY_TIMEOUT,
            )
            return self._normalize_status(result.scalar_one_or_none())

        except asyncio.TimeoutError:
            logger.warning(
                "Timeout getting tenant status by user_id=%s is_tenant=%s", user_id, is_tenant
            )
            return None
        except SQLAlchemyError as exc:
            logger.warning(
                "Multi-tenant DB error getting tenant status by user_id=%s is_tenant=%s: %s",
                user_id,
                is_tenant,
                exc,
            )
            return None
        except ImportError:
            try:
                from libs.ai4icore_multi_tenant.ai4icore_multi_tenant.models import Tenant, TenantUser

                if is_tenant:
                    stmt_admin = select(Tenant.status).where(Tenant.user_id == user_id).limit(1)
                    result = await asyncio.wait_for(db.execute(stmt_admin), timeout=_TENANT_QUERY_TIMEOUT)
                    status = self._normalize_status(result.scalar_one_or_none())
                    if status is not None:
                        return status

                    stmt_admin_via_tenant_user = (
                        select(Tenant.status)
                        .select_from(TenantUser)
                        .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                        .where(TenantUser.user_id == user_id)
                        .limit(1)
                    )
                    result = await asyncio.wait_for(db.execute(stmt_admin_via_tenant_user), timeout=_TENANT_QUERY_TIMEOUT)
                    return self._normalize_status(result.scalar_one_or_none())

                stmt_user = (
                    select(Tenant.status)
                    .select_from(TenantUser)
                    .join(Tenant, TenantUser.tenant_uuid == Tenant.id)
                    .where(TenantUser.user_id == user_id)
                    .limit(1)
                )
                result = await asyncio.wait_for(db.execute(stmt_user), timeout=_TENANT_QUERY_TIMEOUT)
                return self._normalize_status(result.scalar_one_or_none())
            except ImportError:
                return None
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout getting tenant status by user_id (fallback path) user_id=%s is_tenant=%s",
                    user_id,
                    is_tenant,
                )
                return None
            except SQLAlchemyError as exc:
                logger.warning(
                    "Multi-tenant DB error getting tenant status by user_id (fallback path) user_id=%s: %s",
                    user_id,
                    exc,
                )
                return None
        finally:
            if callable(self._session_or_factory):
                await db.close()

    async def debug_tenant_mappings(
        self, tenant_id: str, user_id: int, is_tenant: bool
    ) -> dict[str, Any]:
        """
        Extra observability when tenant status lookup fails.
        Returns presence/status samples from both tenants and tenant_users.
        """
        db = await self._get_session()
        if db is None:
            return {"multi_tenant_db_connected": False}

        tenant_id_norm = (tenant_id or "").strip().lower()
        out: dict[str, Any] = {"multi_tenant_db_connected": True}

        try:
            try:
                from ai4icore_multi_tenant import Tenant, TenantUser
            except ImportError:
                from libs.ai4icore_multi_tenant.ai4icore_multi_tenant.models import Tenant, TenantUser

            # tenants row matched by tenant_id
            stmt_tenant_by_id = (
                select(Tenant.status, Tenant.user_id)
                .where(func.lower(func.trim(Tenant.tenant_id)) == tenant_id_norm)
                .limit(1)
            )
            res = await asyncio.wait_for(
                db.execute(stmt_tenant_by_id), timeout=_TENANT_QUERY_TIMEOUT
            )
            row = res.first()
            out["tenant_by_tenant_id"] = {
                "found": row is not None,
                "status": self._normalize_status(row[0]) if row else None,
                "tenant_user_id": row[1] if row else None,
            }

            # tenants row matched by tenant admin user_id
            stmt_tenant_by_user = (
                select(Tenant.status, Tenant.tenant_id)
                .where(Tenant.user_id == user_id)
                .limit(1)
            )
            res2 = await asyncio.wait_for(
                db.execute(stmt_tenant_by_user), timeout=_TENANT_QUERY_TIMEOUT
            )
            row2 = res2.first()
            out["tenant_by_user_id"] = {
                "found": row2 is not None,
                "status": self._normalize_status(row2[0]) if row2 else None,
                "tenant_id": row2[1] if row2 else None,
            }

            # tenant_user row matched by user_id (works for tenant users and sometimes tenant admins)
            stmt_tenant_user = (
                select(TenantUser.status, TenantUser.tenant_id)
                .where(TenantUser.user_id == user_id)
                .limit(1)
            )
            res3 = await asyncio.wait_for(
                db.execute(stmt_tenant_user), timeout=_TENANT_QUERY_TIMEOUT
            )
            row3 = res3.first()
            out["tenant_user_by_user_id"] = {
                "found": row3 is not None,
                "status": self._normalize_status(row3[0]) if row3 else None,
                "tenant_id": row3[1] if row3 else None,
                "is_tenant_flag": is_tenant,
            }

            return out

        except asyncio.TimeoutError:
            return {**out, "debug_timeout": True}
        except SQLAlchemyError as exc:
            return {**out, "debug_db_error": str(exc)}
        except ImportError:
            return {**out, "debug_import_error": True}
        finally:
            if callable(self._session_or_factory):
                await db.close()
