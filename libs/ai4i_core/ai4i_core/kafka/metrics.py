"""Prometheus metrics of the notification pipeline."""

from prometheus_client import Counter

CACHE_REQUESTS = Counter(
    "ntf_cache_requests_total",
    "Notification cache lookups by cache, layer (L1, L2, L3) and result.",
    ["cache", "layer", "result"],
)
DECISIONS = Counter(
    "ntf_decisions_total",
    "Evaluation outcomes (FIRE, RESET, SKIP, DUPLICATE) per notification.",
    ["name", "decision"],
)
PUBLISHES = Counter(
    "ntf_publish_total",
    "Kafka hand-offs per notification and result.",
    ["name", "result"],
)
FAILURES = Counter(
    "ntf_failure_log_total",
    "Producer-side failures written to notification_alert_failure_log.",
    ["stage", "error_code"],
)
