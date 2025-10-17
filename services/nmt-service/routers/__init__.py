"""
NMT Service Routers Package
"""

from routers.inference_router import router as inference_router
from routers.health_router import router as health_router

__all__ = ["inference_router", "health_router"]
