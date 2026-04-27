"""Tenant lifecycle status checks used by the token validation route."""

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_TENANT_QUERY_TIMEOUT = 5.0
_TENANT_STATUS_CACHE_TTL_SECONDS = 60


def _normalize_status(status_val: Any) -> Optional[str]:
    if status_val is None:
        return None
    return str(getattr(status_val, "value", status_val)).strip().upper()


def is_suspended_or_deactivated(status_val: Any) -> bool:
    return _normalize_status(status_val) in {"SUSPENDED", "DEACTIVATED"}


class TenantService:
    def __init__(self, db: AsyncSession, cache_service: CacheService) -> None:
        self._db = db
        self._cache_service = cache_service

    async def get_tenant_status(self, tenant_id: str) -> Optional[str]:
        if not tenant_id:
            return None
        try:
            tenant_uuid = UUID(str(tenant_id))
        except (ValueError, AttributeError):
            return None

        try:
            result = await asyncio.wait_for(
                self._db.execute(
                    select(Tenant.status).where(Tenant.id == tenant_uuid).limit(1)
                ),
                timeout=_TENANT_QUERY_TIMEOUT,
            )
            return _normalize_status(result.scalar_one_or_none())
        except asyncio.TimeoutError:
            logger.warning("Timeout getting tenant status for tenant_id=%s", tenant_id)
            return None
        except OSError as exc:
            logger.warning("Error getting tenant status for tenant_id=%s: %s", tenant_id, exc)
            return None

    async def get_tenant_status_cached(
        self,
        tenant_id: str,
        *,
        ttl_seconds: int = _TENANT_STATUS_CACHE_TTL_SECONDS,
    ) -> Optional[str]:
        tenant_id_norm = (tenant_id or "").strip().lower()
        if not tenant_id_norm:
            return None

        cached = await self._cache_service.get_tenant_status(tenant_id_norm)
        if cached:
            return _normalize_status(cached)

        status = await self.get_tenant_status(tenant_id_norm)
        if status:
            await self._cache_service.set_tenant_status(tenant_id_norm, status, ttl_seconds)
        return status
