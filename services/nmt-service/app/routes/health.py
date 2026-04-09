"""Health endpoints."""
from ai4icore_service_base import create_health_router

router = create_health_router(service_name="nmt-service", version="1.0.2")
