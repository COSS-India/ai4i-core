"""The Usage Dashboard's period filter, as echoed back in every response."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PeriodKey = Literal["today", "yesterday", "last_7_days", "custom"]


class Period(BaseModel):
    """The period a response covers. ``from``/``to`` are IST calendar dates
    (inclusive); ``start``/``end`` are the exact instants queried, in IST
    with an explicit +05:30 offset (``end`` exclusive; for ``today`` it is
    "now", floored to the cache step).
    """
    # `from` is a Python keyword: field from_ with alias, serialized by alias.
    model_config = ConfigDict(populate_by_name=True)

    key: PeriodKey
    from_: str = Field(..., alias="from")
    to: str
    start: str
    end: str
    timezone: str = "Asia/Kolkata"
    # Where the source's data actually starts within the period: start itself
    # when the source covers the whole period, later when it doesn't (data
    # older than Prometheus/OpenSearch retention, or before usage recording
    # began), null when the source has no data for the period at all.
    dataFrom: Optional[str] = None
    # True when the source doesn't cover the whole period, so a zero can mean
    # "no data", not "no usage".
    partial: bool = False
    # True when part of the period's figures are estimates: days before usage
    # recording began, backfilled from Prometheus (requests and units from its
    # daily totals, cost at today's prices). estimatedUntil is where the
    # estimates end (exclusive; IST, +05:30): figures from dataFrom up to it
    # are estimated, from it on recorded. null when nothing is estimated.
    estimated: bool = False
    estimatedUntil: Optional[str] = None
