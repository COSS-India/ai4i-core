"""Display formatting shared by the report email and PDF, so both show the
same figure the same way (AI4IDS-3278).

Empty values follow one rule everywhere:
- "0" (or "₹0") when there was no activity — a real, measured zero;
- NO_RATE ("—") when a rate or share cannot be calculated (nothing to divide by);
- NA ("Not available") when the platform does not capture the figure, or it
  failed to load.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from app.services.usage_report.collector import PlatformHealth

NA = "Not available"
NO_RATE = "—"

Number = Union[int, float, Decimal]


def _short(n: float, units: tuple[tuple[float, float, str], ...]) -> Optional[str]:
    """n (>= 0) in the largest unit it reaches, to two decimals. Each unit
    starts where the one below would round up to its next unit (999,995 is
    "1.00M", not "1000.00K")."""
    for size, starts_at, suffix in units:
        if n >= starts_at:
            return f"{n / size:.2f}{suffix}"
    return None


_COUNT_UNITS = ((1_000_000, 999_995, "M"), (1_000, 1_000, "K"))
_INR_UNITS = ((10_000_000, 9_999_500, " Cr"), (100_000, 99_999.5, " L"))


def count(n: Optional[Number]) -> str:
    """842 -> "842", 2_170 -> "2.17K", 18_400_000 -> "18.40M"."""
    if n is None:
        return NA
    n = round(float(n))
    sign = "-" if n < 0 else ""
    return sign + (_short(abs(n), _COUNT_UNITS) or str(abs(n)))


def inr(amount: Optional[Number]) -> str:
    """Rupees: below ₹1 lakh in full ("₹20,400"), above in Lakh/Crore with two
    decimals ("₹28.70 L", "₹71.20 Cr"). A non-zero amount under ₹1 is "<₹1",
    so it never reads as no spend."""
    if amount is None:
        return NA
    a = float(amount)
    sign = "-" if a < 0 else ""
    a = abs(a)
    short = _short(a, _INR_UNITS)
    if short is not None:
        return f"{sign}₹{short}"
    whole = round(a)
    if whole == 0 and a > 0:
        return f"{sign}<₹1"
    return f"{sign}₹{whole:,}"


def share(value: Optional[float]) -> str:
    """A part of a whole, in whole percent: 0 -> "0%", 0.3 -> "<1%",
    99.6 -> ">99%", 42.4 -> "42%", 130 -> "130%". None (nothing to divide
    by) -> "—"."""
    if value is None:
        return NO_RATE
    if 0 < value < 1:
        return "<1%"
    if 99 < value < 100:
        return ">99%"
    return f"{round(value)}%"


def pct(value: Optional[float], digits: int = 1) -> str:
    return NO_RATE if value is None else f"{value:.{digits}f}%"


def signed_pct(value: Optional[float]) -> str:
    """+18%, -4.5% — for a change against the previous period."""
    if value is None:
        return NO_RATE
    return f"{value:+.1f}".rstrip("0").rstrip(".") + "%"


def signed_int(value: Optional[int]) -> str:
    return NA if value is None else f"{value:+d}"


def latency_ms(value: Optional[float]) -> str:
    """Whole milliseconds: 639.6 -> "640 ms", 4055 -> "4,055 ms"."""
    return NO_RATE if value is None else f"{round(value):,} ms"


def platform_health(health: Optional["PlatformHealth"]) -> dict[str, str]:
    """The four Platform Health figures. Availability is not captured. With
    no requests in the period the others are "—"; latency P95 and fallback
    rate are "Not available" when the period has none recorded (see
    PlatformHealth.tracked_from); everything is when health failed to load."""
    values = {"availability": NA, "latency_p95": NA, "error_rate": NA, "fallback_rate": NA}
    if health is None:
        return values
    if not health.requests:
        return {**values, "latency_p95": NO_RATE, "error_rate": NO_RATE, "fallback_rate": NO_RATE}
    values["error_rate"] = pct(health.error_rate_pct)
    if health.tracked_from is not None:
        values["latency_p95"] = latency_ms(health.latency_p95_ms)
        values["fallback_rate"] = pct(health.fallback_rate_pct)
    return values
