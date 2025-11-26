"""
AI4I Observability Package

Shared observability library for AI4I microservices.
Provides standardized metrics, middleware, and tenant resolution across all services.

Usage:
    from ai4i_observability import init_observability, default_tenant_resolver
    
    app = FastAPI()
    init_observability(
        app,
        service_name="nmt",
        tenant_resolver=default_tenant_resolver,
        enable_enterprise=True
    )
"""

from .config import ObservabilityConfig, load_config
from .middleware import RequestMetricsMiddleware
from .metrics import (
    bind_registry,
    record_translation,
    record_tts_characters,
    record_asr_seconds,
    record_inference_request,
)
from .tenant import default_tenant_resolver, TenantContext

__version__ = "0.1.0"

# Main initialization function
def init_observability(
    app,
    service_name: str,
    tenant_resolver=None,
    enable_enterprise: bool = True,
    config: ObservabilityConfig = None,
):
    """
    Initialize observability for a FastAPI application.
    
    This function:
    - Registers request metrics middleware (counts, durations)
    - Mounts /metrics endpoint (and /enterprise/metrics if enabled)
    - Exposes business metric helpers
    - Sets up tenant context resolution
    
    Args:
        app: FastAPI application instance
        service_name: Name of the service (e.g., "nmt", "tts", "asr")
        tenant_resolver: Optional function to extract tenant info from Request.
                        Defaults to default_tenant_resolver (JWT/headers)
        enable_enterprise: If True, mounts /enterprise/metrics endpoint
        config: Optional ObservabilityConfig instance. If None, loads from env vars.
    
    Returns:
        CollectorRegistry: The Prometheus registry used for metrics
    
    Example:
        ```python
        from fastapi import FastAPI
        from ai4i_observability import init_observability
        
        app = FastAPI()
        init_observability(app, service_name="nmt")
        ```
    """
    from prometheus_client import CollectorRegistry, make_asgi_app
    from fastapi import FastAPI
    
    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    
    # Load configuration
    if config is None:
        config = load_config()
    
    # Create Prometheus registry
    registry = CollectorRegistry()
    
    # Bind metrics to this registry
    bind_registry(registry, service_name)
    
    # Import here to avoid circular imports
    from .middleware import RequestMetricsMiddleware
    
    # Resolve tenant resolver
    if tenant_resolver is None:
        tenant_resolver = default_tenant_resolver
    
    # Add request metrics middleware
    app.add_middleware(
        RequestMetricsMiddleware,
        registry=registry,
        service_name=service_name,
        tenant_resolver=tenant_resolver,
        path_templating=config.path_templating,
        request_buckets=config.request_buckets,
    )
    
    # Mount /metrics endpoint
    metrics_app = make_asgi_app(registry=registry)
    app.mount("/metrics", metrics_app)
    
    # Mount /enterprise/metrics if enabled
    if enable_enterprise:
        app.mount("/enterprise/metrics", metrics_app)
    
    return registry


__all__ = [
    "init_observability",
    "default_tenant_resolver",
    "TenantContext",
    "ObservabilityConfig",
    "load_config",
    "record_translation",
    "record_tts_characters",
    "record_asr_seconds",
    "record_inference_request",
    "__version__",
]

