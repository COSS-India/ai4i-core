"""The Usage Dashboard's period filter: ``period`` + ``from``/``to`` → the
IST-day range every dashboard endpoint reports on.

    today        IST midnight → now (now floored to the response-cache step)
    yesterday    the previous IST day
    last_7_days  the 7 IST days ending yesterday (today excluded)
    custom       IST days ``from`` … ``to`` inclusive, ``to`` at most yesterday

Prometheus / OpenSearch figures query the range as an AbsoluteRange.
Postgres figures come from usage_events for ``today`` and from daily_usage
for every other period (see ``uses_daily_usage``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, status

from app.schemas.period import Period
from app.utils.metering_promql_builder import AbsoluteRange

IST = ZoneInfo("Asia/Kolkata")
PERIOD_KEYS = ("today", "yesterday", "last_7_days", "custom")
DEFAULT_PERIOD = "today"
# Longest custom range, in days (inclusive).
MAX_CUSTOM_DAYS = 366
# Earliest accepted `from`: the platform has no data before it, and it keeps
# previous-period arithmetic (from − range length) well inside datetime's range.
EARLIEST_FROM = date(2000, 1, 1)
# "now" is floored to this step for `today`, so callers within the same
# minute share one cache entry (and one set of backend queries).
NOW_STEP_SECONDS = 60
# Query params the period filter replaced; still sending one is a 422.
REMOVED_PARAMS = ("window", "billing_period")

PERIOD_DESCRIPTION = "today | yesterday | last_7_days | custom (IST days). Default today."
FROM_DESCRIPTION = "First IST day, YYYY-MM-DD, inclusive. Only with period=custom."
TO_DESCRIPTION = "Last IST day, YYYY-MM-DD, inclusive; yesterday or earlier. Only with period=custom."


def invalid_period(message: str) -> HTTPException:
    """422 with the platform's ``{"detail": {"code", "message"}}`` envelope."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "INVALID_PERIOD", "message": message},
    )


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
        """Postgres source: daily_usage for whole past days, usage_events for today."""
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

    def to_schema(self) -> Period:
        return Period(
            key=self.key,
            from_=self.from_date.isoformat(),
            to=self.to_date.isoformat(),
            start=iso_ist(self.start),
            end=iso_ist(self.end),
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
) -> UsagePeriod:
    """Validate the period params and resolve them to IST days and UTC bounds.
    Every failure is a 422 ``INVALID_PERIOD``."""
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
            start = ist_midnight(today)
            floored = datetime.fromtimestamp(
                int(now.timestamp()) // NOW_STEP_SECONDS * NOW_STEP_SECONDS, tz=timezone.utc,
            )
            # In the first minute after midnight the floor would empty the range.
            end = floored if floored > start else now
            return UsagePeriod(key, today, today, start, end)
        first = yesterday if key == "yesterday" else today - timedelta(days=7)
        return UsagePeriod(key, first, yesterday, ist_midnight(first), ist_midnight(today))

    if from_ is None or to is None:
        raise invalid_period("from and to are required when period is custom.")
    first, last = _parse_date("from", from_), _parse_date("to", to)
    if last >= today:
        raise invalid_period("to must be yesterday or earlier; use period=today for today.")
    if first > last:
        raise invalid_period("from must not be after to.")
    if first < EARLIEST_FROM:
        raise invalid_period(f"from must be on or after {EARLIEST_FROM.isoformat()}.")
    if (last - first).days + 1 > MAX_CUSTOM_DAYS:
        raise invalid_period(f"The custom range must not exceed {MAX_CUSTOM_DAYS} days.")
    return UsagePeriod(key, first, last, ist_midnight(first), ist_midnight(last + timedelta(days=1)))


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
    return resolve_period(period, from_, to, now=now)
