"""Where a Usage Dashboard period's Postgres figures come from.

``today`` reads usage_events (one row per billed span, occurred_at in
[start, end)); every other period reads daily_usage (the rollup, usage_date
between the period's first and last IST day). Both tables carry the same
unit and cost columns; only the time column, the total-cost column and the
unit-label column are named differently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.sql.elements import ColumnElement

from app.models.pay_per_use.daily_usage import DailyUsage
from app.models.pay_per_use.usage_event import UsageEvent
from app.utils.usage_period import UsagePeriod


@dataclass(frozen=True)
class PeriodSource:
    model: Any                      # UsageEvent or DailyUsage
    time_column: ColumnElement      # occurred_at / usage_date
    in_period: ColumnElement        # WHERE clause selecting the period's rows
    total_cost: ColumnElement       # total_cost / cost (generated)
    unit: ColumnElement             # unit_of_measurement / unit


def period_source(period: UsagePeriod) -> PeriodSource:
    if period.uses_daily_usage:
        return PeriodSource(
            model=DailyUsage,
            time_column=DailyUsage.usage_date,
            in_period=DailyUsage.usage_date.between(period.from_date, period.to_date),
            total_cost=DailyUsage.cost,
            unit=DailyUsage.unit,
        )
    return PeriodSource(
        model=UsageEvent,
        time_column=UsageEvent.occurred_at,
        in_period=(UsageEvent.occurred_at >= period.start) & (UsageEvent.occurred_at < period.end),
        total_cost=UsageEvent.total_cost,
        unit=UsageEvent.unit_of_measurement,
    )


def tenant_pks(tenant_ids: list[str]) -> list[int]:
    """usage_events/daily_usage.tenant_id is an integer; tenant ids arrive as
    strings (quota_usage, query params)."""
    return [int(t) for t in tenant_ids if t and t.isdigit()]
