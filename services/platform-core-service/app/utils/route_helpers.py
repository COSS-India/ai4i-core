"""Shared helpers used across list-endpoint route handlers."""

from datetime import date, datetime
from typing import Annotated, Any, List, Optional

from pydantic import BeforeValidator

DATE_PARAM_HELP = (
    "Either an ISO date (YYYY-MM-DD, a whole UTC day) or an ISO datetime with offset "
    "(e.g. 2026-01-05T00:00:00+05:30, an exact instant; no offset means UTC). "
    "URL-encode '+' as %2B."
)


def _parse_date_or_datetime(value: Any) -> Any:
    """A bare YYYY-MM-DD stays a calendar date (a whole UTC day); anything with
    a time is a datetime that keeps its UTC offset. Pydantic's own union would
    read 2026-01-05T00:00:00+05:30 as the date 2026-01-05 and drop the offset."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    return datetime.fromisoformat(value)


DateOrDatetime = Annotated[date | datetime, BeforeValidator(_parse_date_or_datetime)]


def split_csv(value: Optional[str]) -> List[str]:
    """Split a comma-separated query value into stripped, lowercased, non-empty items."""
    if not value:
        return []
    return [part for part in (p.strip().lower() for p in value.split(",")) if part]
