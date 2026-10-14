"""Where a Usage Dashboard period's Postgres figures come from.

usage_events (one row per billed span, occurred_at in [start, end)) serves
``today``. Past periods read daily_usage (usage_date, the IST day, between
the period's first and last day) while USAGE_DAILY_ROLLUP_ENABLED is on (the
default), and usage_events too when it's off. Both tables carry the same unit and cost columns; only the time
column, the total-cost column and the unit-label column are named
differently.
"""
from __future__ import annotations

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


async def usage_data_from(db: AsyncSession, period: UsagePeriod) -> Optional[datetime]:
    """When the data period_source(period) reads begins inside ``period``:
    ``period.start`` when the table holds rows from before it (the period is
    fully covered), else the first row inside the period, else None (no data
    for the period at all). Platform-wide on purpose: it marks when recording
    began, so a period before it reads as "no data" rather than as "no usage"
    for any one institution.

    Bounded on purpose — never min() over the whole table, which no index on
    usage_events can answer (BRIN can't serve a min) and would scan every
    partition: the "anything earlier?" probe stops at the first row it finds
    (partitions older than the period hold rows whenever it's covered), and
    the in-period min() only runs when there's nothing earlier, reading no
    more than the period query itself does (via the occurred_at BRIN)."""
    source = period_source(period)
    if source.model is DailyUsage:
        before = DailyUsage.usage_date < period.from_date
    else:
        before = UsageEvent.occurred_at < period.start
    if await db.scalar(select(source.time_column).where(before).limit(1)) is not None:
        return period.start
    first = await db.scalar(select(func.min(source.time_column)).where(source.in_period))
    if first is None:
        return None
    if not isinstance(first, datetime):  # daily_usage.usage_date: an IST day
        first = datetime.combine(first, day_start(), tzinfo=IST).astimezone(timezone.utc)
    return first
