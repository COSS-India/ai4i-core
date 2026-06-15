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


def sum_over_window(metric_expr: str, time_range: str | None) -> str:
    """Build a PromQL sum-delta query using offset subtraction instead of increase().

    increase() misses new series that first appear mid-window (Prometheus never saw
    the 0→N transition, so it returns 0 for all samples = no change).
    Offset subtraction correctly handles this: if the series didn't exist at the
    start of the window, the implied previous value is 0.
    Falls back to a plain sum for time_range="all"/None.
    """
    window = TIME_RANGES.get(time_range or "all")
    if not window:
        return f"sum({metric_expr})"
    return (
        f"(sum({metric_expr}) or vector(0))"
        f" - (sum({metric_expr} offset {window}) or vector(0))"
    )


def build_base_selectors(
    inference_only: bool = True,
    tenant: str | None = None,
    service_id: str | None = None,
    extra: list[str] | None = None,
) -> str:
    """Build a PromQL label selector string for telemetry_obsv_requests_total.

    Returns a brace-enclosed string like '{endpoint=~"...",tenant="foo"}'
    or an empty string when no filters apply.
    """
    selectors: list[str] = []
    if inference_only:
        selectors.append(f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"')
        selectors.append('method="POST"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')
    if extra:
        selectors.extend(extra)
    return "{" + ",".join(selectors) + "}" if selectors else ""
