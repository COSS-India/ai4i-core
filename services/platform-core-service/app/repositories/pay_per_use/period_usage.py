"""Where a Usage Dashboard period's Postgres figures come from.

usage_events (one row per billed span, occurred_at in [start, end)) serves
``today``, and every other period too until the daily_usage rollup is
switched on (USAGE_DAILY_ROLLUP_ENABLED). With it on, past periods read
daily_usage (usage_date, the IST day, between the period's first and last
day). Both tables carry the same unit and cost columns; only the time
column, the total-cost column and the unit-label column are named
differently.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, time as day_start, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.pay_per_use.daily_usage import DailyUsage
from app.models.pay_per_use.usage_event import UsageEvent
from app.utils.usage_period import IST, UsagePeriod


@dataclass(frozen=True)
class PeriodSource:
    model: Any                      # UsageEvent or DailyUsage
    time_column: ColumnElement      # occurred_at / usage_date
    in_period: ColumnElement        # WHERE clause selecting the period's rows
    total_cost: ColumnElement       # total_cost / cost (generated)
    unit: ColumnElement             # unit_of_measurement / unit


def daily_rollup_enabled() -> bool:
    return settings.usage_daily_rollup_enabled


def period_source(period: UsagePeriod) -> PeriodSource:
    if period.uses_daily_usage and daily_rollup_enabled():
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


# usage_data_since() cache: the earliest recorded usage only moves on a
# backfill, so a found value is kept for an hour; "none yet" is never cached.
_DATA_SINCE_TTL_S = 3600
_data_since: tuple[datetime, float] | None = None


async def usage_data_since(db: AsyncSession) -> Optional[datetime]:
    """When the Postgres usage data begins: the first usage_events row, or,
    with the rollup on, the first daily_usage day if that's earlier. None
    while nothing has been recorded. Platform-wide on purpose: it marks when
    recording began, so a period before it reads as "no data" rather than as
    "no usage" for any one institution."""
    global _data_since
    if _data_since is not None and time.monotonic() < _data_since[1]:
        return _data_since[0]
    candidates = [await db.scalar(select(func.min(UsageEvent.occurred_at)))]
    if daily_rollup_enabled():
        first_day = await db.scalar(select(func.min(DailyUsage.usage_date)))
        if first_day is not None:
            candidates.append(datetime.combine(first_day, day_start(), tzinfo=IST).astimezone(timezone.utc))
    present = [c for c in candidates if c is not None]
    if not present:
        return None
    since = min(present)
    _data_since = (since, time.monotonic() + _DATA_SINCE_TTL_S)
    return since
