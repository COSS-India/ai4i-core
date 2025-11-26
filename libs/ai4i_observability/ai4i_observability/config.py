"""
Configuration management for observability package.
Loads settings from environment variables with sensible defaults.
"""

import os
from typing import List
from dataclasses import dataclass


@dataclass
class ObservabilityConfig:
    """Configuration for observability features"""
    
    # Request duration histogram buckets (in seconds)
    request_buckets: List[float]
    
    # Enable path templating to reduce cardinality
    # e.g., /api/v1/users/123 -> /api/v1/users/:id
    path_templating: bool
    
    # Enable enterprise metrics endpoint
    enable_enterprise: bool
    
    # Metrics namespace prefix
    metrics_namespace: str
    
    # Scrape interval hint (for documentation, not enforced)
    scrape_interval_seconds: int


def load_config() -> ObservabilityConfig:
    """
    Load observability configuration from environment variables.
    
    Environment Variables:
        AI4I_METRICS_BUCKETS: Comma-separated histogram buckets (default: "0.05,0.1,0.3,0.5,1,2,5")
        AI4I_PATH_TEMPLATING: Enable path templating (default: "true")
        AI4I_ENABLE_ENTERPRISE: Enable /enterprise/metrics endpoint (default: "true")
        AI4I_METRICS_NAMESPACE: Prefix for metric names (default: "ai4i")
        AI4I_SCRAPE_INTERVAL: Prometheus scrape interval hint in seconds (default: "5")
    
    Returns:
        ObservabilityConfig: Configuration instance
    """
    # Parse histogram buckets
    buckets_str = os.getenv("AI4I_METRICS_BUCKETS", "0.05,0.1,0.3,0.5,1,2,5")
    try:
        request_buckets = [float(b.strip()) for b in buckets_str.split(",")]
    except ValueError:
        # Fallback to default buckets
        request_buckets = [0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
    
    # Parse boolean flags
    path_templating = os.getenv("AI4I_PATH_TEMPLATING", "true").lower() == "true"
    enable_enterprise = os.getenv("AI4I_ENABLE_ENTERPRISE", "true").lower() == "true"
    
    # Metrics namespace
    metrics_namespace = os.getenv("AI4I_METRICS_NAMESPACE", "ai4i")
    
    # Scrape interval
    scrape_interval = int(os.getenv("AI4I_SCRAPE_INTERVAL", "5"))
    
    return ObservabilityConfig(
        request_buckets=request_buckets,
        path_templating=path_templating,
        enable_enterprise=enable_enterprise,
        metrics_namespace=metrics_namespace,
        scrape_interval_seconds=scrape_interval,
    )

