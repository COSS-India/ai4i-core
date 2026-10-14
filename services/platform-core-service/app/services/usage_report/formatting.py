"""Display formatting shared by the report email and PDF, so both show the
same figure the same way."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

NA = "N/A"

Number = Union[int, float, Decimal]


def count(n: Optional[Number]) -> str:
    """18_400_000 -> "18.4M", 973_100 -> "973.1K", 42 -> "42"."""
    if n is None:
        return NA
    n = float(n)
    for size, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(n) >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{n:.0f}"


def indian(n: Optional[Number]) -> str:
    """Indian-system short form: 590_000 -> "5.9 L", 21_50_00_000 -> "21.5 Cr"."""
    if n is None:
        return NA
    n = float(n)
    for size, suffix in ((10_000_000, " Cr"), (100_000, " L"), (1_000, "K")):
        if abs(n) >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{n:.0f}"


def inr(amount: Optional[Number]) -> str:
    """₹ amount in Lakh/Crore: Decimal("215000000") -> "₹21.5 Cr"."""
    return NA if amount is None else f"₹{indian(amount)}"


def pct(value: Optional[float], digits: int = 1) -> str:
    return NA if value is None else f"{value:.{digits}f}%"


def signed_pct(value: Optional[float]) -> str:
    """+18%, -4.5% — for a change against the previous period."""
    if value is None:
        return NA
    return f"{value:+.1f}".rstrip("0").rstrip(".") + "%"


def signed_int(value: Optional[int]) -> str:
    return NA if value is None else f"{value:+d}"
