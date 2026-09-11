"""Pure threshold-crossing math for QUOTA_THRESHOLD/BUDGET_THRESHOLD/
QUOTA_EXHAUSTED/BUDGET_EXHAUSTED.

The configured % bands themselves (and whether a notification is even
enabled) come from ai4i_core.kafka.notification_settings_cache — the same
shared, pub/sub-refreshed cache auth-service and platform-core-service use —
not from anything local to this module. See main.py for where that cache is
initialized and kept listening.
"""
from decimal import Decimal
from typing import List, Optional


def crossed_bands(pre_pct: Decimal, post_pct: Decimal, bands: List[int]) -> List[int]:
    """Every configured band whose percent falls in (pre_pct, post_pct] —
    i.e. every band this debit newly pushed usage past."""
    return [band for band in bands if pre_pct < band <= post_pct]


def crossed_exhaustion(pre_pct: Decimal, post_pct: Decimal) -> bool:
    """True exactly on the <100% -> >=100% transition caused by this debit."""
    return pre_pct < 100 <= post_pct


def percent(used: Optional[Decimal], snap: Optional[Decimal]) -> Optional[Decimal]:
    """used/snap as a 0-100 percentage; None when there's no ceiling to
    measure against (unlimited/no row)."""
    if used is None or snap is None or snap == 0:
        return None
    return (used / snap) * 100
