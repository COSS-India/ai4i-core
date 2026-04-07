"""
ai4icore_service_base -- Shared infrastructure for AI4I-Core inference services.

Provides common building blocks that every inference service needs:
- ServiceRegistryClient: register/deregister with central service discovery
- RateLimitMiddleware: Redis-based per-API-key rate limiting
- health_router: standard health/ready/live endpoints
"""

from .service_registry import ServiceRegistryClient
from .rate_limit import RateLimitMiddleware
from .health import create_health_router

# Lazy import: create_inference_app depends on ai4icore_model_management
# which is not installed in non-inference services (e.g. pipeline-service).
def __getattr__(name):
    if name == "create_inference_app":
        from .app_factory import create_inference_app
        return create_inference_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ServiceRegistryClient",
    "RateLimitMiddleware",
    "create_health_router",
    "create_inference_app",
]
