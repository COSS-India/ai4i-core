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

__all__ = [
    "ServiceRegistryClient",
    "RateLimitMiddleware",
    "create_health_router",
]
