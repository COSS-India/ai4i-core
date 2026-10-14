"""Reporting periods for the Usage Viewer report.

The frequency is configuration, not code: USAGE_REPORT_FREQUENCY (set on the
pyjob `usage_report` job) is either
``monthly`` (calendar months) or any duration — ``30m``, ``2h``, ``1d``,
``3d``, ``7d``, ``14d`` … (units m, h, d, w). A duration's periods are
back-to-back blocks of that length counted from one fixed anchor, IST
midnight of Monday 5 Jan 2026 (ANCHOR), so ``1d`` is an IST day, ``7d`` Monday to
Sunday and ``14d`` the same fortnight for everyone. The old names still work:
daily = 1d, weekly = 7d, fortnightly = 14d, hourly = 1h, 30min = 30m.

Like the other pyjob jobs, the period is derived from the current time, not
from when the job last ran, so a late or repeated run reports the same
clean period.

Whole-day periods resolve through the Usage Dashboard's own period filter (a
``custom`` range, app.utils.usage_period.resolve_period), so the report
covers exactly what the dashboard shows for them; shorter or day-straddling
blocks read usage_events by timestamp.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.utils.usage_period import IST, UsagePeriod, ist_midnight, resolve_period

MONTHLY = "monthly"
DEFAULT_FREQUENCY = MONTHLY  # when the job sends none
HALF_HOURLY, HOURLY, DAILY, WEEKLY, FORTNIGHTLY = "30m", "1h", "1d", "7d", "14d"
# Fixed, not configurable: changing it after reports were sent would shift every
# period. A Monday, so 7d blocks run Monday to Sunday.
ANCHOR = date(2026, 1, 5)
MIN_LENGTH = timedelta(minutes=5)
DAY = timedelta(days=1)

ALIASES = {
    "30min": HALF_HOURLY, "half-hourly": HALF_HOURLY, "hourly": HOURLY,
    "daily": DAILY, "weekly": WEEKLY, "fortnightly": FORTNIGHTLY, "month": MONTHLY,
}
# Wording for common lengths: (email title, noun for "vs previous …").
_NAMES = {
    HALF_HOURLY: ("30-minute", "30 minutes"), HOURLY: ("Hourly", "hour"),
    DAILY: ("Daily", "day"), WEEKLY: ("Weekly", "week"), FORTNIGHTLY: ("Fortnightly", "fortnight"),
}
_UNITS = {"m": ("minute", timedelta(minutes=1)), "h": ("hour", timedelta(hours=1)),
          "d": ("day", DAY), "w": ("week", timedelta(weeks=1))}
_DURATION_RE = re.compile(r"^(\d+)\s*(m|min|h|d|w)$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
# A block counts as complete only this long after it ends, so Prometheus
# scrapes and usage_events writes for its last minutes are in.
SETTLE = timedelta(minutes=2)
# UsagePeriod.key that makes period_source read usage_events by occurred_at;
# any other key reads daily_usage by whole IST days once the rollup is on.
_EVENTS_KEY = "today"


@dataclass(frozen=True)
class Frequency:
    name: str                      # canonical: "monthly", or "<n><m|h|d>" e.g. "7d"
    length: Optional[timedelta]    # None for monthly

    @classmethod
    def parse(cls, value: str) -> "Frequency":
        raw = (value or "").strip().lower()
        raw = ALIASES.get(raw, raw)
        if raw == MONTHLY:
            return cls(MONTHLY, None)
        m = _DURATION_RE.match(raw)
        if not m:
            raise ValueError(
                f"frequency must be 'monthly' or a duration like 30m, 2h, 1d, 7d, 14d; got {value!r}"
            )
        n, unit = int(m.group(1)), m.group(2)[0]
        length = n * _UNITS[unit][1]
        if length < MIN_LENGTH:
            raise ValueError(f"frequency must be at least {int(MIN_LENGTH.total_seconds() // 60)} minutes; got {value!r}")
        return cls(_canonical(length), length)

    @property
    def is_monthly(self) -> bool:
        return self.length is None

    @property
    def is_subdaily(self) -> bool:
        """Shorter than a day — test environments only."""
        return self.length is not None and self.length < DAY

    @property
    def title(self) -> str:
        if self.is_monthly:
            return "Monthly"
        if self.name in _NAMES:
            return _NAMES[self.name][0]
        n, word = _count_and_unit(self.length)
        return f"{n}-{word}"

    @property
    def noun(self) -> str:
        if self.name in _NAMES:
            return _NAMES[self.name][1]
        n, word = _count_and_unit(self.length)
        return f"{n} {word}s"


def _count_and_unit(length: timedelta) -> tuple[int, str]:
    """Largest of day / hour / minute that divides the length exactly."""
    for unit in ("d", "h", "m"):
        word, size = _UNITS[unit]
        if length % size == timedelta(0):
            return length // size, word
    raise AssertionError("lengths are whole minutes")


def _canonical(length: timedelta) -> str:
    n, word = _count_and_unit(length)
    return f"{n}{word[0]}"


def check_frequency(value: str) -> str:
    """Validate a configured frequency; returns its canonical name ("7d", "monthly")."""
    return Frequency.parse(value).name


def _month_after(day: date) -> date:
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def _ist(dt: datetime) -> datetime:
    return dt.astimezone(IST)


@dataclass(frozen=True)
class ReportPeriod:
    frequency: str    # canonical (see Frequency)
    start: datetime   # UTC, inclusive
    end: datetime     # UTC, exclusive

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def days(cls, frequency: str, first_day: date, last_day: date) -> "ReportPeriod":
        """Whole IST days first_day … last_day."""
        return cls(check_frequency(frequency), ist_midnight(first_day), ist_midnight(last_day + DAY))

    @classmethod
    def month(cls, year: int, month: int) -> "ReportPeriod":
        first = date(year, month, 1)
        return cls.days(MONTHLY, first, _month_after(first) - DAY)

    @classmethod
    def parse_month(cls, value: str) -> "ReportPeriod":
        """"YYYY-MM" -> that calendar month. ValueError on any other shape."""
        m = _MONTH_RE.match(value.strip())
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise ValueError(f"period must be YYYY-MM, got {value!r}")
        return cls.month(int(m.group(1)), int(m.group(2)))

    @classmethod
    def containing(cls, frequency: str, when, anchor: date = ANCHOR) -> "ReportPeriod":
        """The period of ``frequency`` that ``when`` (an instant, or an IST
        day meaning its midnight) falls in."""
        freq = Frequency.parse(frequency)
        instant = ist_midnight(when) if not isinstance(when, datetime) else when
        if freq.is_monthly:
            day = _ist(instant).date()
            return cls.month(day.year, day.month)
        origin = ist_midnight(anchor)
        start = origin + (instant - origin) // freq.length * freq.length
        return cls(freq.name, start, start + freq.length)

    @classmethod
    def latest_complete(
        cls, frequency: str, now: Optional[datetime] = None, anchor: date = ANCHOR
    ) -> "ReportPeriod":
        """The most recent period that ended at least SETTLE ago."""
        cutoff = (now or datetime.now(timezone.utc)) - SETTLE
        period = cls.containing(frequency, cutoff, anchor)
        return period.previous() if period.end > cutoff else period

    # ── properties ──────────────────────────────────────────────────────────

    @property
    def freq(self) -> Frequency:
        return Frequency.parse(self.frequency)

    @property
    def is_subdaily(self) -> bool:
        return self.freq.is_subdaily

    @property
    def whole_days(self) -> bool:
        """Starts and ends at IST midnight (the dashboard's day periods)."""
        return self.start == ist_midnight(self.first_day) and self.end == ist_midnight(self.last_day + DAY)

    @property
    def first_day(self) -> date:
        """First IST day the period touches."""
        return _ist(self.start).date()

    @property
    def last_day(self) -> date:
        """Last IST day the period touches."""
        return _ist(self.end - timedelta(microseconds=1)).date()

    @property
    def day_count(self) -> Optional[int]:
        """Whole IST days in the period; None when it isn't whole days."""
        return (self.last_day - self.first_day).days + 1 if self.whole_days else None

    def previous(self) -> "ReportPeriod":
        """The period of the same frequency just before this one."""
        if self.frequency == MONTHLY:
            last = self.first_day - DAY
            return ReportPeriod.month(last.year, last.month)
        length = self.end - self.start
        return ReportPeriod(self.frequency, self.start - length, self.end - length)

    def usage_period(self, now: Optional[datetime] = None) -> UsagePeriod:
        """The period as the dashboard's period. ValueError for one that hasn't
        ended yet (whole days: the dashboard's rule, ``to`` at most yesterday)."""
        if not self.whole_days:
            if self.end > (now or datetime.now(timezone.utc)):
                raise ValueError(f"{self.label}: has not ended yet")
            return UsagePeriod(_EVENTS_KEY, self.first_day, self.last_day, self.start, self.end)
        try:
            return resolve_period("custom", self.first_day.isoformat(), self.last_day.isoformat(), now=now)
        except HTTPException as exc:
            message = exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail
            raise ValueError(f"{self.label}: {message}") from None

    # ── wording ─────────────────────────────────────────────────────────────

    @property
    def title(self) -> str:
        """The email subject's frequency word: "Monthly", "Weekly", "2-hour"."""
        return self.freq.title

    @property
    def month_name(self) -> str:
        return self.first_day.strftime("%B")

    @property
    def date_span(self) -> str:
        """e.g. "1–30 Sep 2026", "29 Sep – 5 Oct 2026", "13 Oct 2026",
        "14 Oct 2026, 10:00–10:30 IST", "13 Oct 22:00 – 14 Oct 2026 10:00 IST"."""
        a, b = self.first_day, self.last_day
        if not self.whole_days:
            s, e = _ist(self.start), _ist(self.end)
            if a == b:
                return f"{a:%-d %b %Y}, {s:%H:%M}–{e:%H:%M} IST"
            return f"{s:%-d %b %H:%M} – {e:%-d %b %Y %H:%M} IST"
        if a == b:
            return f"{a:%-d %b %Y}"
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
        """For tight spaces: "Sep", "13 Oct", "29 Sep–5 Oct", "10:00–10:30"."""
        a, b = self.first_day, self.last_day
        if self.frequency == MONTHLY:
            return f"{a:%b}"
        if not self.whole_days:
            s, e = _ist(self.start), _ist(self.end)
            return f"{s:%H:%M}–{e:%H:%M}" if a == b else f"{s:%-d %b %H:%M}–{e:%-d %b %H:%M}"
        if a == b:
            return f"{a:%-d %b}"
        return f"{a:%-d %b}–{b:%-d %b}" if a.month != b.month else f"{a.day}–{b.day} {b:%b}"

    @property
    def in_phrase(self) -> str:
        """"in September" / "this week" / "on 13 Oct" / "in this period"."""
        if self.frequency == MONTHLY:
            return f"in {self.month_name}"
        if self.frequency == DAILY:
            return f"on {self.first_day:%-d %b}"
        if self.frequency in (WEEKLY, FORTNIGHTLY):
            return f"this {self.freq.noun}"
        return "in this period"

    @property
    def vs_phrase(self) -> str:
        """Comparison against the previous period: "vs August" / "vs previous week"."""
        if self.frequency == MONTHLY:
            return f"vs {self.previous().month_name}"
        return f"vs previous {self.freq.noun}"

    @property
    def key(self) -> str:
        """Filename-safe: "2026-09", "2026-10-13", "2026-09-29_2026-10-05",
        "2026-10-14T10-00_10-30", "2026-10-13T22-00_2026-10-14T10-00"."""
        a, b = self.first_day, self.last_day
        if self.frequency == MONTHLY:
            return f"{a:%Y-%m}"
        if not self.whole_days:
            s, e = _ist(self.start), _ist(self.end)
            return f"{s:%Y-%m-%dT%H-%M}_{e:%H-%M}" if a == b else f"{s:%Y-%m-%dT%H-%M}_{e:%Y-%m-%dT%H-%M}"
        return a.isoformat() if a == b else f"{a.isoformat()}_{b.isoformat()}"
