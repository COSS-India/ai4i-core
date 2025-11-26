"""
Request metrics middleware.
Automatically records request counts and durations for all HTTP requests.
"""

import time
import logging
from typing import Callable, Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from prometheus_client import CollectorRegistry, Counter, Histogram

logger = logging.getLogger(__name__)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records request metrics for all HTTP requests.
    
    Records:
    - Request count (Counter): method, endpoint, status_code, service, organization
    - Request duration (Histogram): method, endpoint, service, organization
    
    The middleware extracts tenant context using the provided tenant_resolver
    and stores it in request.state.ai4i_tenant for use in handlers.
    """
    
    def __init__(
        self,
        app,
        registry: CollectorRegistry,
        service_name: str,
        tenant_resolver: Callable[[Request], Dict[str, str]],
        path_templating: bool = True,
        request_buckets: Optional[List[float]] = None,
    ):
        """
        Initialize request metrics middleware.
        
        Args:
            app: ASGI application
            registry: Prometheus CollectorRegistry
            service_name: Name of the service (e.g., "nmt", "tts", "asr")
            tenant_resolver: Function to extract tenant context from Request
            path_templating: If True, use route path templates to reduce cardinality
            request_buckets: Histogram buckets for request duration (default: [0.05, 0.1, 0.3, 0.5, 1, 2, 5])
        """
        super().__init__(app)
        self.registry = registry
        self.service_name = service_name
        self.tenant_resolver = tenant_resolver
        self.path_templating = path_templating
        
        # Default buckets if not provided
        if request_buckets is None:
            request_buckets = [0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0]
        
        # Create metrics
        self.request_count = Counter(
            "ai4i_requests_total",
            "Total HTTP requests",
            labelnames=("method", "endpoint", "status_code", "service", "organization"),
            registry=registry,
        )
        
        self.request_duration = Histogram(
            "ai4i_request_duration_seconds",
            "HTTP request duration in seconds",
            labelnames=("method", "endpoint", "service", "organization"),
            buckets=request_buckets,
            registry=registry,
        )
    
    def _get_endpoint_path(self, request: Request) -> str:
        """
        Get endpoint path, using route template if path_templating is enabled.
        
        Args:
            request: FastAPI Request object
        
        Returns:
            str: Endpoint path (template or actual)
        """
        if self.path_templating and hasattr(request, "scope"):
            route = request.scope.get("route")
            if route and hasattr(route, "path"):
                # Use route template (e.g., /api/v1/users/{user_id})
                return route.path
        # Fallback to actual path
        return request.url.path
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and record metrics.
        
        Args:
            request: FastAPI Request object
            call_next: Next middleware/handler in chain
        
        Returns:
            Response: HTTP response
        """
        # Extract tenant context
        try:
            tenant = self.tenant_resolver(request)
            # Store in request.state for use in handlers
            request.state.ai4i_tenant = tenant
        except Exception as e:
            logger.warning(f"Failed to resolve tenant context: {e}")
            # Use default tenant context
            from .tenant import TenantContext
            tenant = TenantContext(
                organization="unknown",
                user_id="anonymous",
                api_key_name="unknown",
            )
            request.state.ai4i_tenant = tenant
        
        # Get endpoint path
        endpoint = self._get_endpoint_path(request)
        
        # Start timer
        start_time = time.perf_counter()
        
        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Record error
            status_code = 500
            logger.error(f"Request failed: {e}", exc_info=True)
            raise
        finally:
            # Calculate duration
            duration = time.perf_counter() - start_time
            
            # Record metrics
            try:
                labels = (
                    request.method,
                    endpoint,
                    str(status_code),
                    self.service_name,
                    tenant.organization,
                )
                self.request_count.labels(*labels).inc()
                
                duration_labels = (
                    request.method,
                    endpoint,
                    self.service_name,
                    tenant.organization,
                )
                self.request_duration.labels(*duration_labels).observe(duration)
            except Exception as e:
                logger.warning(f"Failed to record metrics: {e}")
        
        return response

