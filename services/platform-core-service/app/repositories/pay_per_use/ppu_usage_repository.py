"""PPU usage repository — reads usage and pricing data."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_usage_with_pricing(self, billing_month: str):
        """
        Aggregates units_used per inference_name for the billing month,
        left-joined with mm_services pricing via billing_unit_type.
        """
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                Service.cost_per_unit,
                Service.unit_size,
                Service.unit_rate,
            )
            .outerjoin(
                Service,
                (Service.billing_unit_type == PPUQuotaUsage.inference_name)
                & Service.deleted_at.is_(None),
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
            .group_by(
                PPUQuotaUsage.inference_name,
                Service.cost_per_unit,
                Service.unit_size,
                Service.unit_rate,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()
