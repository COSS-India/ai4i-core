"""Reporting period for the Usage Viewer report: one calendar month.

Resolved through the Usage Dashboard's own period filter (a ``custom``
range of IST days, app.utils.usage_period.resolve_period), so a month in the
report covers exactly the requests and spend the dashboard shows for it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.utils.usage_period import IST, UsagePeriod, resolve_period

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True)
class ReportMonth:
    year: int
    month: int

    @classmethod
    def parse(cls, value: str) -> "ReportMonth":
        """"YYYY-MM" -> ReportMonth. ValueError on any other shape."""
        m = _MONTH_RE.match(value.strip())
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise ValueError(f"period must be YYYY-MM, got {value!r}")
        return cls(int(m.group(1)), int(m.group(2)))

    @classmethod
    def last_complete(cls, now: Optional[datetime] = None) -> "ReportMonth":
        """The month before the current IST month."""
        today = (now or datetime.now(timezone.utc)).astimezone(IST).date()
        return cls(today.year, today.month).previous()

    def previous(self) -> "ReportMonth":
        return ReportMonth(self.year - 1, 12) if self.month == 1 else ReportMonth(self.year, self.month - 1)

    def next(self) -> "ReportMonth":
        return ReportMonth(self.year + 1, 1) if self.month == 12 else ReportMonth(self.year, self.month + 1)

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def last_day(self) -> date:
        return self.next().first_day - timedelta(days=1)

    def usage_period(self, now: Optional[datetime] = None) -> UsagePeriod:
        """The month as the dashboard's period. ValueError for a month that
        hasn't ended yet (the dashboard's own rule: ``to`` at most yesterday)."""
        try:
            return resolve_period(
                "custom", self.first_day.isoformat(), self.last_day.isoformat(), now=now
            )
        except HTTPException as exc:
            message = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
            raise ValueError(f"{self.label}: {message}") from None

    @property
    def month_name(self) -> str:
        return self.first_day.strftime("%B")

    @property
    def label(self) -> str:
        """e.g. "August 2026"."""
        return f"{self.month_name} {self.year}"

    @property
    def key(self) -> str:
        """e.g. "2026-08"."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def date_span(self) -> str:
        """e.g. "1–31 Aug 2026"."""
        return f"1–{self.last_day.day} {self.first_day:%b} {self.year}"
