"""The Usage Dashboard's period filter: ``period`` + ``from``/``to`` → the
IST-day range every dashboard endpoint reports on.

    today        IST midnight → now (now floored to the response-cache step)
    yesterday    the previous IST day
    last_7_days  the 7 IST days ending today: the 6 before it, and today up to now
    custom       IST days ``from`` … ``to`` inclusive, ``to`` at most today
                 (a range ending today runs up to now)

That's the dashboard's filter (period_from_request). Other callers of
resolve_period (the usage report) keep the earlier rule unless they pass
include_today: last_7_days ends yesterday, and a custom ``to`` must be
yesterday or earlier.

Prometheus / OpenSearch figures query the range as an AbsoluteRange.
Postgres figures come from usage_events, or, once the rollup is on, from
daily_usage for the whole past days and usage_events for today up to now
(see period_usage.period_sources).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, status

from app.schemas.period import Period
from app.utils.metering_promql_builder import AbsoluteRange

IST = ZoneInfo("Asia/Kolkata")
PERIOD_KEYS = ("today", "yesterday", "last_7_days", "custom")
DEFAULT_PERIOD = "today"
# Earliest accepted `from`: the platform has no data before it, and it keeps
# previous-period arithmetic (from − range length) well inside datetime's range.
EARLIEST_FROM = date(2000, 1, 1)
# "now" is floored to this step for a period ending today, so callers within
# the same minute share one cache entry (and one set of backend queries).
NOW_STEP_SECONDS = 60
# Query params the period filter replaced; still sending one is a 422.
REMOVED_PARAMS = ("window", "billing_period")

PERIOD_DESCRIPTION = "today | yesterday | last_7_days | custom (IST days). Default today."
FROM_DESCRIPTION = "First IST day, YYYY-MM-DD, inclusive. Only with period=custom."
TO_DESCRIPTION = "Last IST day, YYYY-MM-DD, inclusive; today or earlier (today counts up to now). Only with period=custom."


def invalid_period(message: str) -> HTTPException:
    """422 with the platform's ``{"detail": {"code", "message"}}`` envelope."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "INVALID_PERIOD", "message": message},
    )


class _FullCoverage:
    """to_schema's default: the source covers the whole period."""

    __slots__ = ()


FULL_COVERAGE = _FullCoverage()


@dataclass(frozen=True)
class UsagePeriod:
    key: str
    from_date: date          # first IST day, inclusive
    to_date: date            # last IST day, inclusive
    start: datetime          # UTC, inclusive
    end: datetime            # UTC, exclusive

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    @property
    def uses_daily_usage(self) -> bool:
        """Whether daily_usage can serve the period's whole past days once the
        rollup is on (period_usage.period_sources decides; today, up to now,
        always comes from usage_events)."""
        return self.key != "today"

    @property
    def absolute_range(self) -> AbsoluteRange:
        """The range for Prometheus / OpenSearch queries. The previous period
        (KPI comparisons) is the same IST days, ``days`` earlier: for ``today``
        that's yesterday midnight → the same clock time yesterday."""
        return AbsoluteRange(
            start=self.start, end=self.end, previous_shift_seconds=self.days * 86_400,
        )

    @property
    def cache_part(self) -> str:
        return f"{self.key}:{int(self.start.timestamp())}-{int(self.end.timestamp())}"

    def to_schema(self, data_since: Union[datetime, None, _FullCoverage] = FULL_COVERAGE) -> Period:
        """The response's period block. ``data_since`` is when the figures'
        source starts having data: the Prometheus/OpenSearch retention edge,
        or the first recorded usage event. FULL_COVERAGE (the default) means
        the whole period is covered; None means the source has no data."""
        if isinstance(data_since, _FullCoverage):
            data_from, partial = self.start, False
        elif data_since is None or data_since >= self.end:
            data_from, partial = None, True
        else:
            data_from = max(self.start, data_since)
            partial = data_from > self.start
        return Period(
            key=self.key,
            from_=self.from_date.isoformat(),
            to=self.to_date.isoformat(),
            start=iso_ist(self.start),
            end=iso_ist(self.end),
            dataFrom=iso_ist(data_from) if data_from else None,
            partial=partial,
        )


def iso_ist(dt: datetime) -> str:
    """ISO-8601 in IST with its offset, e.g. 2026-10-12T00:00:00+05:30 — the
    format of every timestamp the Usage Dashboard API returns: the same
    instant as the UTC value, written in the dashboard users' timezone."""
    return dt.astimezone(IST).isoformat(timespec="seconds")


def ist_midnight(day: date) -> datetime:
    """IST 00:00 of ``day``, in UTC."""
    return datetime.combine(day, time(), tzinfo=IST).astimezone(timezone.utc)


def _parse_date(name: str, raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise invalid_period(f"{name} must be a date in YYYY-MM-DD format.") from None


def resolve_period(
    period: Optional[str],
    from_: Optional[str],
    to: Optional[str],
    *,
    now: Optional[datetime] = None,
    include_today: bool = False,
) -> UsagePeriod:
    """Validate the period params and resolve them to IST days and UTC bounds.
    Every failure is a 422 ``INVALID_PERIOD``. ``include_today`` (the
    dashboard's filter) lets last_7_days and a custom range end today, up to
    now; without it they end yesterday at the latest."""
    key = (period or DEFAULT_PERIOD).strip()
    if key not in PERIOD_KEYS:
        raise invalid_period("period must be one of: today, yesterday, last_7_days, custom.")
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    yesterday = today - timedelta(days=1)

    if key != "custom":
        if from_ is not None or to is not None:
            raise invalid_period("from and to are only allowed when period is custom.")
        if key == "today":
            return UsagePeriod(key, today, today, ist_midnight(today), _floored_now(now, today))
        if key == "yesterday":
            return UsagePeriod(key, yesterday, yesterday, ist_midnight(yesterday), ist_midnight(today))
        if not include_today:
            first = today - timedelta(days=7)
            return UsagePeriod(key, first, yesterday, ist_midnight(first), ist_midnight(today))
        first = today - timedelta(days=6)
        return UsagePeriod(key, first, today, ist_midnight(first), _floored_now(now, today))

    if from_ is None or to is None:
        raise invalid_period("from and to are required when period is custom.")
    first, last = _parse_date("from", from_), _parse_date("to", to)
    if include_today:
        if last > today:
            raise invalid_period("to must be today or earlier.")
    elif last >= today:
        raise invalid_period("to must be yesterday or earlier; use period=today for today.")
    if first > last:
        raise invalid_period("from must not be after to.")
    if first < EARLIEST_FROM:
        raise invalid_period(f"from must be on or after {EARLIEST_FROM.isoformat()}.")
    end = _floored_now(now, today) if last == today else ist_midnight(last + timedelta(days=1))
    return UsagePeriod(key, first, last, ist_midnight(first), end)


def _floored_now(now: datetime, today: date) -> datetime:
    """The end of a period running up to now: now floored to NOW_STEP_SECONDS,
    so requests within the same step share one cache entry. In the first step
    after midnight the floor would empty today, so it's now itself then."""
    floored = datetime.fromtimestamp(int(now.timestamp()) // NOW_STEP_SECONDS * NOW_STEP_SECONDS, tz=timezone.utc)
    return floored if floored > ist_midnight(today) else now


def reject_removed_params(request: Request) -> None:
    """The period filter replaced ``window`` and ``billing_period``; a caller
    still sending one gets a clear 422 instead of having it silently ignored."""
    query_params = getattr(request, "query_params", None) or {}
    for name in REMOVED_PARAMS:
        if name in query_params:
            raise invalid_period(f"{name} is no longer supported; use period.")


def period_from_request(
    request: Request,
    period: Optional[str],
    from_: Optional[str],
    to: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> UsagePeriod:
    """The period filter for one dashboard request: rejects the removed
    params, then resolves period/from/to (422 INVALID_PERIOD on bad input)."""
    reject_removed_params(request)
    return resolve_period(period, from_, to, now=now, include_today=True)
