"""
NMT Service Routers Package
"""

from .inference_router import inference_router
from .health_router import health_router
from .try_it_router import try_it_router

__all__ = ["inference_router", "health_router", "try_it_router"]
