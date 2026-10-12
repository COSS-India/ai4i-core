"""Application-level usage repository.

All-time spend comes from budget_usage, keyed by api_key_id only (no
application_id, no billing_month — see BudgetUsage model). Spend in a Usage
Dashboard period comes from usage_events / daily_usage (see period_usage).
Rolling either up to application/tenant level is done by the service layer,
which resolves api_key -> application -> tenant via auth_db.
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.budget_usage import BudgetUsage
from app.repositories.pay_per_use.period_usage import period_source
from app.utils.usage_period import UsagePeriod


class ApplicationUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_spend_by_api_key_ids(self, api_key_ids: list[int]) -> dict[int, Decimal]:
        """{api_key_id: api_key_budget_used} for the given keys.

        A key with no budget_usage row yet (spend hasn't accrued, or the
        write path hasn't caught up) is simply absent — callers treat that
        as spend=0.
        """
        if not api_key_ids:
            return {}
        stmt = select(BudgetUsage.api_key_id, BudgetUsage.api_key_budget_used).where(
            BudgetUsage.api_key_id.in_(api_key_ids)
        )
        result = await self._db.execute(stmt)
        return {row.api_key_id: row.api_key_budget_used or Decimal("0") for row in result.all()}

    async def get_period_spend_by_api_key_ids(
        self, period: UsagePeriod, api_key_ids: list[int],
    ) -> dict[int, Decimal]:
        """{api_key_id: spend in ``period``} for the given keys — usage_events
        for ``today``, daily_usage otherwise. A key with no usage in the
        period is absent (spend 0)."""
        if not api_key_ids:
            return {}
        source = period_source(period)
        m = source.model
        stmt = (
            select(m.api_key_id, func.sum(source.total_cost).label("spend"))
            .where(source.in_period, m.api_key_id.in_(api_key_ids))
            .group_by(m.api_key_id)
        )
        result = await self._db.execute(stmt)
        return {row.api_key_id: row.spend or Decimal("0") for row in result.all()}
