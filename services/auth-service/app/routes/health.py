"""
Health endpoints — re-exports from shared ai4icore_bootstrap.
"""

from ai4icore_bootstrap.health import create_health_router

router = create_health_router(service_name="auth-service", version="2.0.0")
