"""Reporting periods for the Usage Viewer report: weekly, fortnightly, monthly.

All periods are whole IST days and are resolved through the Usage Dashboard's
own period filter (a ``custom`` range, app.utils.usage_period.resolve_period),
so a period in the report covers exactly what the dashboard shows for it.

- weekly:      Monday to Sunday.
- fortnightly: 14-day blocks counted from an anchor Monday
               (USAGE_REPORT_FORTNIGHT_ANCHOR), so every fortnight is the
               same two weeks for everyone.
- monthly:     calendar months.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.utils.usage_period import IST, UsagePeriod, resolve_period

WEEKLY, FORTNIGHTLY, MONTHLY = "weekly", "fortnightly", "monthly"
FREQUENCIES = (WEEKLY, FORTNIGHTLY, MONTHLY)
DEFAULT_FORTNIGHT_ANCHOR = date(2026, 1, 5)  # a Monday

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def check_frequency(value: str) -> str:
    frequency = (value or "").strip().lower()
    if frequency not in FREQUENCIES:
        raise ValueError(f"frequency must be one of {', '.join(FREQUENCIES)}, got {value!r}")
    return frequency


def _month_after(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


@dataclass(frozen=True)
class ReportPeriod:
    frequency: str
    first_day: date   # IST day, inclusive
    last_day: date    # IST day, inclusive

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def month(cls, year: int, month: int) -> "ReportPeriod":
        first = date(year, month, 1)
        return cls(MONTHLY, first, _month_after(first) - timedelta(days=1))

    @classmethod
    def parse_month(cls, value: str) -> "ReportPeriod":
        """"YYYY-MM" -> that calendar month. ValueError on any other shape."""
        m = _MONTH_RE.match(value.strip())
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise ValueError(f"period must be YYYY-MM, got {value!r}")
        return cls.month(int(m.group(1)), int(m.group(2)))

    @classmethod
    def containing(cls, frequency: str, day: date, anchor: date = DEFAULT_FORTNIGHT_ANCHOR) -> "ReportPeriod":
        """The period of ``frequency`` that ``day`` falls in."""
        frequency = check_frequency(frequency)
        if frequency == MONTHLY:
            return cls.month(day.year, day.month)
        if frequency == WEEKLY:
            first = day - timedelta(days=day.weekday())
            return cls(WEEKLY, first, first + timedelta(days=6))
        first = anchor + timedelta(days=(day - anchor).days // 14 * 14)
        return cls(FORTNIGHTLY, first, first + timedelta(days=13))

    @classmethod
    def latest_complete(
        cls, frequency: str, now: Optional[datetime] = None, anchor: date = DEFAULT_FORTNIGHT_ANCHOR
    ) -> "ReportPeriod":
        """The most recent period that ended before today (IST)."""
        today = (now or datetime.now(timezone.utc)).astimezone(IST).date()
        return cls.containing(frequency, today - timedelta(days=1), anchor).previous_if_ends_after(today)

    def previous_if_ends_after(self, today: date) -> "ReportPeriod":
        return self.previous() if self.last_day >= today else self

    # ── navigation ──────────────────────────────────────────────────────────

    def previous(self) -> "ReportPeriod":
        """The period of the same frequency just before this one."""
        if self.frequency == MONTHLY:
            last = self.first_day - timedelta(days=1)
            return ReportPeriod.month(last.year, last.month)
        length = timedelta(days=self.days)
        return ReportPeriod(self.frequency, self.first_day - length, self.last_day - length)

    @property
    def days(self) -> int:
        return (self.last_day - self.first_day).days + 1

    def usage_period(self, now: Optional[datetime] = None) -> UsagePeriod:
        """The period as the dashboard's period. ValueError for one that hasn't
        ended yet (the dashboard's own rule: ``to`` at most yesterday)."""
        try:
            return resolve_period("custom", self.first_day.isoformat(), self.last_day.isoformat(), now=now)
        except HTTPException as exc:
            message = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
            raise ValueError(f"{self.label}: {message}") from None

    # ── wording ─────────────────────────────────────────────────────────────

    @property
    def title(self) -> str:
        """e.g. "Monthly" — the email subject's frequency word."""
        return self.frequency.capitalize()

    @property
    def month_name(self) -> str:
        return self.first_day.strftime("%B")

    @property
    def date_span(self) -> str:
        """e.g. "1–30 Sep 2026", "29 Sep – 5 Oct 2026", "29 Dec 2025 – 11 Jan 2026"."""
        a, b = self.first_day, self.last_day
        if a.year != b.year:
            return f"{a:%-d %b %Y} – {b:%-d %b %Y}"
        if a.month != b.month:
            return f"{a:%-d %b} – {b:%-d %b %Y}"
        return f"{a.day}–{b.day} {b:%b %Y}"

    @property
    def label(self) -> str:
        """"September 2026" for a month, else the date span."""
        return f"{self.month_name} {self.first_day.year}" if self.frequency == MONTHLY else self.date_span

    @property
    def short_label(self) -> str:
        """For tight spaces: "Sep" for a month, else the date span without the year."""
        if self.frequency == MONTHLY:
            return f"{self.first_day:%b}"
        a, b = self.first_day, self.last_day
        return f"{a:%-d %b}–{b:%-d %b}" if a.month != b.month else f"{a.day}–{b.day} {b:%b}"

    @property
    def in_phrase(self) -> str:
        """"in September" / "this week" / "this fortnight"."""
        return f"in {self.month_name}" if self.frequency == MONTHLY else f"this {self.frequency[:-2]}"

    @property
    def vs_phrase(self) -> str:
        """Comparison against the previous period: "vs August" / "vs previous week"."""
        if self.frequency == MONTHLY:
            return f"vs {self.previous().month_name}"
        return f"vs previous {self.frequency[:-2]}"

    @property
    def key(self) -> str:
        """Filename-safe: "2026-09" for a month, else "2026-09-29_2026-10-05"."""
        if self.frequency == MONTHLY:
            return f"{self.first_day:%Y-%m}"
        return f"{self.first_day.isoformat()}_{self.last_day.isoformat()}"
