"""
These will be class methods and they will need a platform_core_db for creating the session at runtime.
Pass session method not the session in the init.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from ai4i_core.exceptions import ValidationError
from app.core.database import get_platform_core_db

logger = logging.getLogger(__name__)


class PpuTenantTierAssignmentsRepository:

    @staticmethod
    async def get_tier_by_tenant_id(tenant_id: str) -> str:
        async with asynccontextmanager(get_platform_core_db)() as platform_core_db:
            if platform_core_db is None:
                raise ValidationError(
                    message="Tier assignment cannot be verified: platform-core DB is not configured.",
                    code="PLATFORM_CORE_DB_NOT_CONFIGURED",
                )
            try:
                row = (await platform_core_db.execute(
                    text(
                        "SELECT tier_id FROM ppu_tenant_tier_assignments"
                        " WHERE tenant_id = :tenant_id"
                        "   AND effective_from <= now()"
                        "   AND effective_to   >  now()"
                        " LIMIT 1"
                    ),
                    {"tenant_id": tenant_id},
                )).first()
                tier_id = str(row.tier_id) if row else ""
            except Exception as exc:
                logger.warning("Failed to fetch tier_id for tenant %s: %s", tenant_id, exc)
                raise ValidationError(
                    message="Failed to verify tier assignment for the tenant.",
                    code="TIER_LOOKUP_FAILED",
                ) from exc
            if not tier_id:
                raise ValidationError(
                    message="API key cannot be created: tenant has no active tier assignment.",
                    code="NO_ACTIVE_TIER",
                )
            return tier_id

    @staticmethod
    async def get_active_tier_and_balance_quota_details(
        tenant_id: str,
    ) -> tuple[str, Decimal, dict[str, bool]]:
        """Return (tier_id, available_balance, quota_exhausted_map) for the tenant's active tier.

        quota_exhausted_map maps inference_name -> exhausted (bool), one entry for every
        inference type that has a monthly_quota configured in ppu_tier_quotas for this tier.
        exhausted is True when units_used (from ppu_quota_usage for the current billing
        month, defaulting to 0 if no usage row exists yet) has reached or exceeded
        monthly_quota. Inference types with no quota row for this tier are omitted from the
        map (treated as unlimited), matching the convention kafka-consumers'
        update_quota_usage already uses.
        """

        async with asynccontextmanager(get_platform_core_db)() as platform_core_db:
            if platform_core_db is None:
                raise ValidationError(
                    message="Tier assignment cannot be verified: platform-core DB is not configured.",
                    code="PLATFORM_CORE_DB_NOT_CONFIGURED",
                )
            try:
                # Get tier_id and available balance for the tenant from ppu_tenant_tier_assignments
                row = await platform_core_db.execute(
                    text(
                        "SELECT tier_id, available_balance FROM ppu_tenant_tier_assignments"
                        " WHERE tenant_id = :tenant_id"
                        "   AND effective_from <= now()"
                        "   AND effective_to   >  now()"
                        " ORDER BY effective_from DESC"
                        " LIMIT 1"
                    ),
                    {"tenant_id": tenant_id},
                )
            except Exception as exc:
                logger.error("Failed to fetch tier_id for tenant %s: %s", tenant_id, exc)
                raise exc
            row = row.first()
            if not row:
                raise ValidationError(
                    message="API key cannot be created: tenant has no active tier assignment.",
                    code="NO_ACTIVE_TIER",
                )
            tier_id, available_balance = row[0], row[1]

            billing_month = datetime.now(timezone.utc).strftime("%Y-%m")
            try:
                # Now get the ppu_tier_quotas with usage for each using left join on tier_quotas
                quota_rows = (await platform_core_db.execute(
                    text(
                        "SELECT tq.inference_name, tq.monthly_quota,"
                        "       COALESCE(qu.units_used, 0) AS units_used"
                        "  FROM ppu_tier_quotas tq"
                        "  LEFT JOIN ppu_quota_usage qu"
                        "    ON qu.tier_id = tq.tier_id"
                        "   AND qu.inference_name = tq.inference_name"
                        "   AND qu.tenant_id = :tenant_id"
                        "   AND qu.billing_month = :billing_month"
                        " WHERE tq.tier_id = :tier_id"
                    ),
                    {"tenant_id": tenant_id, "billing_month": billing_month, "tier_id": tier_id},
                )).all()
            except Exception as exc:
                logger.error("Failed to fetch quotas for tier for tenant %s: %s", tenant_id, exc)
                raise exc
            if not row:
                raise ValidationError(
                    message="We could not find monthly quota for this tier.",
                    code="NO_ACTIVE_QUOTA_FOR_TIER")
            quota_exhausted_map = {
                r.inference_name: r.units_used >= r.monthly_quota for r in quota_rows
            }

            return tier_id, available_balance, quota_exhausted_map
