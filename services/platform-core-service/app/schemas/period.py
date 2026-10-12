"""The Usage Dashboard's period filter, as echoed back in every response."""
from typing import Literal

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
