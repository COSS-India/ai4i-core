"""PromQL helpers for the metering API — pure functions, no DB, no I/O.

Provides:
  - ``TIME_RANGES``: allowed time-window keys mapped to Prometheus duration strings.
  - ``INFERENCE_ENDPOINT_REGEX``: regex that matches all inference endpoints.
  - ``apply_time_range``: wraps a metric expression in ``increase(...[window])``.
"""

from __future__ import annotations

# Allowed time range values mapped to Prometheus duration strings.
# None means no window — returns the cumulative counter value.
TIME_RANGES: dict = {
    "1h":  "1h",
    "24h": "24h",
    "7d":  "7d",
    "30d": "30d",
    "all": None,
}

# Regex that matches inference endpoints (POST only).
INFERENCE_ENDPOINT_REGEX = r".*inference.*"


def apply_time_range(metric_expr: str, time_range: str | None) -> str:
    """Wrap metric_expr in increase(...[window]) when a time range is given.

    increase() returns how much the counter grew over the window.
    When time_range is None or 'all', returns the raw cumulative counter.
    """
    window = TIME_RANGES.get(time_range or "all")
    if window:
        return f"increase({metric_expr}[{window}])"
    return metric_expr
