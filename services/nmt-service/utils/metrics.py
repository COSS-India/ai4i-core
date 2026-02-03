"""
Prometheus Metrics for NMT Service with A/B Experiment Labels

These metrics include experiment and variant labels for A/B testing analysis.
"""

import os
from prometheus_client import Counter, Histogram, Gauge, Info, REGISTRY, CollectorRegistry

# Service info
SERVICE_NAME = os.getenv("SERVICE_NAME", "nmt-service")

# Common labels for all metrics
COMMON_LABELS = ["service", "source_language", "target_language"]
EXPERIMENT_LABELS = ["experiment", "variant"]  # For A/B testing

# ============================================================================
# REQUEST METRICS
# ============================================================================

# Total inference requests
NMT_REQUESTS_TOTAL = Counter(
    "nmt_inference_requests_total",
    "Total number of NMT inference requests",
    COMMON_LABELS + EXPERIMENT_LABELS + ["status"]
)

# Request latency histogram with experiment labels
NMT_REQUEST_LATENCY = Histogram(
    "nmt_inference_latency_seconds",
    "NMT inference request latency in seconds",
    COMMON_LABELS + EXPERIMENT_LABELS,
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
)

# Batch size distribution
NMT_BATCH_SIZE = Histogram(
    "nmt_inference_batch_size",
    "Number of texts per inference request",
    COMMON_LABELS + EXPERIMENT_LABELS,
    buckets=[1, 5, 10, 20, 30, 50, 70, 90]
)

# Text length distribution (total characters per request)
NMT_TEXT_LENGTH = Histogram(
    "nmt_inference_text_length_chars",
    "Total text length in characters per request",
    COMMON_LABELS + EXPERIMENT_LABELS,
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000]
)

# ============================================================================
# ERROR METRICS
# ============================================================================

NMT_ERRORS_TOTAL = Counter(
    "nmt_inference_errors_total",
    "Total number of NMT inference errors",
    COMMON_LABELS + EXPERIMENT_LABELS + ["error_type"]
)

# ============================================================================
# TRITON METRICS
# ============================================================================

TRITON_REQUEST_LATENCY = Histogram(
    "nmt_triton_request_latency_seconds",
    "Triton inference latency (model execution time)",
    COMMON_LABELS + EXPERIMENT_LABELS + ["model_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
)

TRITON_BATCH_LATENCY = Histogram(
    "nmt_triton_batch_latency_seconds",
    "Triton batch processing latency",
    COMMON_LABELS + EXPERIMENT_LABELS + ["batch_index"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
)

# ============================================================================
# EXPERIMENT METRICS
# ============================================================================

EXPERIMENT_ASSIGNMENTS = Counter(
    "nmt_experiment_assignments_total",
    "Total experiment variant assignments",
    ["experiment", "variant", "service_id"]
)

EXPERIMENT_RESOLUTION_LATENCY = Histogram(
    "nmt_experiment_resolution_latency_seconds",
    "Time to resolve experiment variant",
    ["experiment"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def record_inference_request(
    source_language: str,
    target_language: str,
    experiment: str,
    variant: str,
    status: str,
    latency_seconds: float,
    batch_size: int,
    text_length: int
):
    """Record metrics for an inference request"""
    labels = {
        "service": SERVICE_NAME,
        "source_language": source_language,
        "target_language": target_language,
        "experiment": experiment or "none",
        "variant": variant or "default",
    }
    
    # Increment request counter
    NMT_REQUESTS_TOTAL.labels(**labels, status=status).inc()
    
    # Record latency
    NMT_REQUEST_LATENCY.labels(**labels).observe(latency_seconds)
    
    # Record batch size
    NMT_BATCH_SIZE.labels(**labels).observe(batch_size)
    
    # Record text length
    NMT_TEXT_LENGTH.labels(**labels).observe(text_length)


def record_inference_error(
    source_language: str,
    target_language: str,
    experiment: str,
    variant: str,
    error_type: str
):
    """Record an inference error"""
    NMT_ERRORS_TOTAL.labels(
        service=SERVICE_NAME,
        source_language=source_language,
        target_language=target_language,
        experiment=experiment or "none",
        variant=variant or "default",
        error_type=error_type
    ).inc()


def record_triton_latency(
    source_language: str,
    target_language: str,
    experiment: str,
    variant: str,
    model_name: str,
    latency_seconds: float
):
    """Record Triton model execution latency"""
    TRITON_REQUEST_LATENCY.labels(
        service=SERVICE_NAME,
        source_language=source_language,
        target_language=target_language,
        experiment=experiment or "none",
        variant=variant or "default",
        model_name=model_name
    ).observe(latency_seconds)


def record_experiment_assignment(
    experiment: str,
    variant: str,
    service_id: str
):
    """Record an experiment variant assignment"""
    EXPERIMENT_ASSIGNMENTS.labels(
        experiment=experiment or "none",
        variant=variant or "default",
        service_id=service_id
    ).inc()


def record_experiment_resolution_latency(experiment: str, latency_seconds: float):
    """Record time taken to resolve experiment variant"""
    EXPERIMENT_RESOLUTION_LATENCY.labels(
        experiment=experiment or "none"
    ).observe(latency_seconds)
