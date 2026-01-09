"""
AI4ICore Model Management Plugin

This package provides reusable model management integration for AI4ICore services,
including Model Management Service client, Triton client, caching, and middleware
for automatic service resolution.

Features:
- Model Management Service client with Redis + in-memory caching
- Generic Triton Inference Server client wrapper
- Model Resolution Middleware for FastAPI
- Automatic serviceId → endpoint + model_name resolution
- Shared caching across service instances
"""

__version__ = "1.0.0"
__author__ = "AI4X Team"
__email__ = "team@ai4x.com"

from .client import ModelManagementClient
from .triton_client import TritonClient
from .middleware import ModelResolutionMiddleware
from .config import ModelManagementConfig
from .plugin import ModelManagementPlugin

__all__ = [
    "ModelManagementClient",
    "TritonClient",
    "ModelResolutionMiddleware",
    "ModelManagementConfig",
    "ModelManagementPlugin",
]

