"""
Routers Package
FastAPI routers for transliteration service
"""

from .inference_router import inference_router
from .health_router import health_router

__all__ = [
    "inference_router",
    "health_router"
]

