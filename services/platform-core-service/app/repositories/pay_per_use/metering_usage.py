"""usage_events / daily_usage reads behind the Usage Dashboard's metering tabs
(Overview, Model consumption) — see UsageEventsMeteringService.

Requests and failures are counted from request rows (one per API-key
request, written from its request span: one row, one request — not distinct
correlation ids, which a client can reuse across calls via X-Correlation-ID),
units from usage rows (see UsageEvent), so a request is counted once whatever
usage rows it has. Rows from before the cut-over (PRE_CUTOVER_ROWS) are
counted by distinct correlation id, as the request they stand in for may have
several. A request is failed when its status is 400 or above. Fallback
requests (sent to a fallback service) are request rows with sent_to_fallback
(daily_usage.fallback_count in the rollup); they are part of the request total,
never added to it. Server errors are failed requests whose status is 500 or
above (server errors and timeouts; daily_usage.server_error_count), part of the
failures.

Whole IST days read the daily_usage rollup when it's enabled and has the day;
everything else — today, partial days at a range's edges, days not rolled up
yet — reads usage_events, so a day missing from the rollup is never shown as
zero. The rollup counts requests the same way (request rows one each,
older status-carrying rows once per correlation id), so both paths agree.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.usage_event import PRE_CUTOVER_ROWS, REQUEST_ROWS
from app.repositories.pay_per_use.period_usage import daily_rollup_enabled
from app.utils.usage_period import IST

# Requests and failed requests among usage_events rows (see the module docstring).
_REQUESTS = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS})"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS})"
)
_FAILED = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS} AND status_code >= 400)"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS} AND status_code >= 400)"
)
_SERVER_ERRORS = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS} AND status_code >= 500)"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS} AND status_code >= 500)"
)
# Requests sent to a fallback service: request rows only (older rows predate the flag).
_FALLBACK = f"count(*) FILTER (WHERE {REQUEST_ROWS} AND sent_to_fallback)"

# Grouping dimensions: (daily_usage expression, usage_events expression).
_GROUPS = {
    "tenant_id": ("tenant_id", "tenant_id"),
    "service_id": ("service_id", "service_id"),
    "inference_type_id": ("inference_type_id", "inference_type_id"),
    "day": ("usage_date", "(occurred_at AT TIME ZONE 'Asia/Kolkata')::date"),
}


@dataclass
class UsageAgg:
    """Requests, failures (server errors among them), requests sent to a
    fallback and units for one group."""
    requests: int = 0
    failed: int = 0
    server_errors: int = 0
    fallback: int = 0
    units: Decimal = field(default_factory=Decimal)
    cached_units: Decimal = field(default_factory=Decimal)
    output_units: Decimal = field(default_factory=Decimal)

    @property
    def successful(self) -> int:
        return self.requests - self.failed

    def add(self, row: Any) -> None:
        self.requests += int(row.requests or 0)
        self.failed += int(row.failed or 0)
        self.server_errors += int(row.server_errors or 0)
        self.fallback += int(row.fallback or 0)
        self.units += Decimal(row.units or 0)
        self.cached_units += Decimal(row.cached_units or 0)
        self.output_units += Decimal(row.output_units or 0)


def _ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST).astimezone(timezone.utc)


def _ist_day(instant: datetime) -> date:
    return instant.astimezone(IST).date()


def _merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(i for i in intervals if i[0] < i[1]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


class MeteringUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        # The metering routes gather several reads at once, and they share one
        # request-scoped AsyncSession, which isn't safe for concurrent use:
        # every query on it goes through this lock.
        self.lock = asyncio.Lock()

    async def _all(self, sql: str, params: dict) -> list:
        async with self.lock:
            return (await self._db.execute(text(sql), params)).all()

    async def _scalar(self, sql: str, params: dict):
        async with self.lock:
            return await self._db.scalar(text(sql), params)

    @staticmethod
    def _filters(tenant_id: Optional[int], type_ids: Optional[list[int]], params: dict) -> str:
        clauses = []
        if tenant_id is not None:
            clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if type_ids is not None:
            clauses.append("inference_type_id = ANY(:type_ids)")
            params["type_ids"] = list(type_ids)
        return "".join(f" AND {c}" for c in clauses)

    @staticmethod
    def _rollup_days(start: datetime, end: datetime) -> list[date]:
        """Whole IST days inside [start, end), today excluded (not complete):
        the days the rollup can answer."""
        if not daily_rollup_enabled():
            return []
        today = _ist_day(datetime.now(timezone.utc))
        day = _ist_day(start)
        if _ist_midnight(day) < start:
            day += timedelta(days=1)
        days = []
        while _ist_midnight(day + timedelta(days=1)) <= end and day < today:
            days.append(day)
            day += timedelta(days=1)
        return days

    async def aggregate(
        self,
        start: datetime,
        end: datetime,
        group_by: tuple[str, ...] = (),
        *,
        tenant_id: Optional[int] = None,
        type_ids: Optional[list[int]] = None,
    ) -> dict[tuple, UsageAgg]:
        """{group key: UsageAgg} over [start, end), grouped by ``group_by``
        (any of tenant_id, service_id, inference_type_id, day — the IST day).
        ``type_ids`` keeps those catalogue types only ([] matches nothing)."""
        result: dict[tuple, UsageAgg] = {}
        days = self._rollup_days(start, end)
        rolled: set[date] = set()

        if days:
            params: dict = {"days": days}
            where = self._filters(tenant_id, type_ids, params)
            cols = [_GROUPS[g][0] for g in group_by]
            select_cols = ", ".join(f"{c} AS g{i}" for i, c in enumerate(cols))
            rows = await self._all(
                f"SELECT usage_date AS d{', ' + select_cols if cols else ''},"
                " sum(request_count) AS requests, sum(failed_count) AS failed,"
                " sum(server_error_count) AS server_errors, sum(fallback_count) AS fallback,"
                " sum(total_units) AS units, sum(cached_input_units) AS cached_units,"
                " sum(output_units) AS output_units"
                f" FROM daily_usage WHERE usage_date = ANY(:days){where}"
                f" GROUP BY usage_date{''.join(', ' + c for c in cols)}",
                params,
            )
            for row in rows:
                rolled.add(row.d)
                key = tuple(getattr(row, f"g{i}") for i in range(len(cols)))
                result.setdefault(key, UsageAgg()).add(row)

        # Everything the rollup didn't answer: partial days at the edges, today,
        # and whole days it has no rows for (not rolled up yet, or no usage).
        intervals = [(start, end)] if not days else [
            (start, _ist_midnight(days[0])),
            (_ist_midnight(days[-1] + timedelta(days=1)), end),
            *((_ist_midnight(d), _ist_midnight(d + timedelta(days=1))) for d in days if d not in rolled),
        ]
        intervals = _merge_intervals(intervals)
        if intervals:
            params = {}
            ranges = []
            for i, (s, e) in enumerate(intervals):
                ranges.append(f"(occurred_at >= :s{i} AND occurred_at < :e{i})")
                params[f"s{i}"], params[f"e{i}"] = s, e
            where = self._filters(tenant_id, type_ids, params)
            exprs = [_GROUPS[g][1] for g in group_by]
            select_cols = "".join(f"{e} AS g{i}, " for i, e in enumerate(exprs))
            group_clause = f" GROUP BY {', '.join(exprs)}" if exprs else ""
            rows = await self._all(
                f"SELECT {select_cols}"
                f" {_REQUESTS} AS requests, {_FAILED} AS failed, {_SERVER_ERRORS} AS server_errors,"
                f" {_FALLBACK} AS fallback,"
                " sum(total_units) AS units, sum(cached_input_units) AS cached_units,"
                " sum(output_units) AS output_units"
                f" FROM usage_events WHERE ({' OR '.join(ranges)}){where}{group_clause}",
                params,
            )
            for row in rows:
                if not exprs and row.requests == 0 and row.units is None:
                    continue  # the ungrouped aggregate over no rows
                key = tuple(getattr(row, f"g{i}") for i in range(len(exprs)))
                result.setdefault(key, UsageAgg()).add(row)
        return result

    async def request_buckets(
        self,
        start: datetime,
        end: datetime,
        step_seconds: int,
        *,
        tenant_id: Optional[int] = None,
        type_ids: Optional[list[int]] = None,
    ) -> dict[int, tuple[int, int]]:
        """{bucket index: (requests, failed)} over [start, end) in buckets of
        ``step_seconds`` from ``start`` — from usage_events, for sub-day steps
        (the rollup has nothing finer than a day)."""
        params: dict = {"start": start, "end": end, "step": step_seconds}
        where = self._filters(tenant_id, type_ids, params)
        rows = await self._all(
            "SELECT floor(extract(epoch FROM occurred_at - :start) / :step)::int AS bucket,"
            f" {_REQUESTS} AS requests, {_FAILED} AS failed"
            f" FROM usage_events WHERE occurred_at >= :start AND occurred_at < :end{where}"
            " GROUP BY 1",
            params,
        )
        return {row.bucket: (int(row.requests), int(row.failed)) for row in rows}

    async def request_rows_from(self, start: datetime, end: datetime) -> Optional[datetime]:
        """When request rows begin inside [start, end): ``start`` when there
        are request rows from before it (fully covered), else the first one
        inside, else None. Both reads use the partial index on request rows
        (ix_usage_events_request_rows), never a scan."""
        before = await self._scalar(
            f"SELECT 1 FROM usage_events WHERE occurred_at < :start AND {REQUEST_ROWS} LIMIT 1",
            {"start": start},
        )
        if before is not None:
            return start
        return await self._scalar(
            f"SELECT min(occurred_at) FROM usage_events"
            f" WHERE occurred_at >= :start AND occurred_at < :end AND {REQUEST_ROWS}",
            {"start": start, "end": end},
        )

    async def fallbacks_recorded_by(self, at: datetime) -> bool:
        """Whether request rows carried the fallback flag by ``at``: the last
        request row before it has a response time, written with the flag (rows
        from before migration ea3961c258e4 have neither). One step back along
        the request-row index (ix_usage_events_request_rows)."""
        return bool(await self._scalar(
            f"SELECT response_time_ms IS NOT NULL FROM usage_events WHERE occurred_at < :at AND {REQUEST_ROWS}"
            " ORDER BY occurred_at DESC LIMIT 1",
            {"at": at},
        ))

    async def response_times_from(self, end: datetime) -> Optional[datetime]:
        """When request rows began carrying a response time (and the fallback
        flag, written with it), if before ``end``; None when not yet. Walks
        the request-row index (ix_usage_events_request_rows) in time order."""
        return await self._scalar(
            f"SELECT occurred_at FROM usage_events WHERE occurred_at < :end AND {REQUEST_ROWS}"
            " AND response_time_ms IS NOT NULL ORDER BY occurred_at LIMIT 1",
            {"end": end},
        )

    async def response_time_p95(self, start: datetime, end: datetime) -> Optional[float]:
        """The 95th-percentile response time (ms) of the requests in
        [start, end), failed ones included; None when none has one. Read from
        usage_events: a percentile can't be combined from daily figures."""
        return await self._scalar(
            "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) FROM usage_events"
            f" WHERE occurred_at >= :start AND occurred_at < :end AND {REQUEST_ROWS}"
            " AND response_time_ms IS NOT NULL",
            {"start": start, "end": end},
        )

    async def first_usage(self, tenant_id: Optional[int]) -> Optional[datetime]:
        """When API-key usage begins: the tenant's first usage_events row (by
        its (tenant_id, occurred_at) index), or platform-wide the first day in
        the rollup — usage_events has no index to answer a platform-wide min.
        The rollup only covers the days since it started running, so rows
        from before its first day are checked too: a range read of just that
        stretch (BRIN). Without a rollup, the whole table is read."""
        if tenant_id is not None:
            return await self._scalar(
                "SELECT min(occurred_at) FROM usage_events WHERE tenant_id = :tenant_id",
                {"tenant_id": tenant_id},
            )
        first_day = (
            await self._scalar("SELECT min(usage_date) FROM daily_usage", {})
            if daily_rollup_enabled() else None
        )
        if first_day is None:
            return await self._scalar("SELECT min(occurred_at) FROM usage_events", {})
        earlier = await self._scalar(
            "SELECT min(occurred_at) FROM usage_events WHERE occurred_at < :before",
            {"before": _ist_midnight(first_day)},
        )
        return earlier or _ist_midnight(first_day)
