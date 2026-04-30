"""
TTS Service Routers Package

This package contains all FastAPI router classes.
"""

from routers.inference_router import inference_router
from routers.health_router import health_router
from routers.voice_router import router as voice_router

__all__ = [
    "inference_router",
    "health_router",
    "voice_router"
]
