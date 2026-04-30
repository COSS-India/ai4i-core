"""Health check endpoints using shared health router."""

from ai4icore_service_base import create_health_router

router = create_health_router(service_name="language-detection-service", version="1.0.0")
