"""Which threshold band an observed value reaches (BAND rule)."""

from typing import Optional, Sequence

from .keys import to_decimal
from .models import Band


def band_for(value, bands: Sequence[Band]) -> Optional[Band]:
    """The highest band whose value is at or below `value`, or None."""
    observed = to_decimal(value)
    reached = [band for band in bands if band.value <= observed]
    return max(reached, key=lambda band: band.value) if reached else None
