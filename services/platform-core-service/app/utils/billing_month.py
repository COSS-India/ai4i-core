"""Shared YYYY-MM billing-month parsing/arithmetic — used by both the PPU usage
service (prior-month comparisons) and repository (end-of-month instant), so any
future fix to the year-rollover logic only has to happen in one place.
"""


def shift_billing_month(billing_month: str, delta_months: int) -> tuple[int, int]:
    """Returns the (year, month) for billing_month shifted by delta_months
    (positive or negative), rolling over the year boundary as needed."""
    year, month = (int(part) for part in billing_month.split("-"))
    total = year * 12 + (month - 1) + delta_months
    year, month0 = divmod(total, 12)
    return year, month0 + 1
