from fastapi import APIRouter

from .config_router import router as config_router
from .service_registry_router import router as service_registry_router
from .health_router import router as health_router
from .feature_flag_router import router as feature_flag_router

__all__ = [
    "APIRouter",
    "config_router",
    "service_registry_router",
    "health_router",
    "feature_flag_router",
]


