"""Prometheus metrics definitions for the profiler service.

These metrics are exposed via the /metrics endpoint for collection by the
existing infrastructure metrics collection service (Prometheus or compatible).
No separate Prometheus container is needed - metrics are scraped by the
centralized monitoring infrastructure.
"""
from prometheus_client import Counter, Histogram, Info

# Request metrics
PROFILE_REQUESTS = Counter(
    "profiler_requests_total",
    "Total profile requests",
    ["domain", "complexity_level", "status"],
)

# Latency metrics
PROFILE_LATENCY = Histogram(
    "profiler_latency_seconds",
    "Profile request latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

# Model version info
MODEL_VERSION = Info(
    "profiler_model",
    "Current model version information",
)

# Text length distribution
TEXT_LENGTH = Histogram(
    "profiler_text_length_words",
    "Distribution of input text lengths in words",
    buckets=[10, 25, 50, 100, 250, 500, 1000, 5000],
)

# Batch processing metrics
BATCH_SIZE = Histogram(
    "profiler_batch_size",
    "Distribution of batch sizes",
    buckets=[1, 5, 10, 20, 30, 40, 50],
)

