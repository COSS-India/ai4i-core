"""Rounding that keeps a breakdown's parts adding up to its total."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence


def round_parts(parts: Sequence[Decimal], total: Decimal, places: int = 2) -> list[Decimal]:
    """Round each part to ``places`` decimals, then add whatever the rounded
    parts are short of (or over) ``total`` — itself rounded the same way — to
    the largest part, so the parts always sum exactly to the rounded total.

    e.g. three parts of 1.004 against a total of 3.012: 1.00 + 1.00 + 1.00 is
    0.01 short of 3.01, so one part becomes 1.01."""
    quantum = Decimal(1).scaleb(-places)
    rounded = [Decimal(p).quantize(quantum, ROUND_HALF_UP) for p in parts]
    if not rounded:
        return rounded
    target = Decimal(total).quantize(quantum, ROUND_HALF_UP)
    residual = target - sum(rounded, Decimal(0))
    if residual:
        largest = max(range(len(parts)), key=lambda i: Decimal(parts[i]))
        rounded[largest] += residual
    return rounded


def round_shares(parts: Sequence[Decimal], places: int = 2) -> list[Decimal]:
    """Each part's percentage of their sum, rounded to ``places`` decimals so
    the shares add up to exactly 100 (all 0 when the sum is 0)."""
    whole = sum((Decimal(p) for p in parts), Decimal(0))
    if not whole:
        return [Decimal(0).quantize(Decimal(1).scaleb(-places)) for _ in parts]
    return round_parts([Decimal(p) / whole * 100 for p in parts], Decimal(100), places)
