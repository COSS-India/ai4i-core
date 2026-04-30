"""
AI4ICore Platform Core Plugin

This package provides reusable platform core integration for AI4ICore services,
including Platform Core Service client, Triton client, caching, and middleware
for automatic service resolution.

Features:
- Platform Core Service client with Redis + in-memory caching
- Generic Triton Inference Server client wrapper
- Model Resolution Middleware for FastAPI
- Automatic serviceId → endpoint + model_name resolution
- Shared caching across service instances
"""

__version__ = "1.0.0"
__author__ = "AI4X Team"
__email__ = "team@ai4x.com"

from .client import PlatformCoreClient, ServiceInfo
from .triton_client import TritonClient, _current_scope, _accumulate_inference_time, SCOPE_KEY
from .middleware import ModelResolutionMiddleware
from .config import PlatformCoreConfig
from .plugin import PlatformCorePlugin

# Backward-compat aliases — existing imports continue to work
ModelManagementClient = PlatformCoreClient
ModelManagementConfig = PlatformCoreConfig
ModelManagementPlugin = PlatformCorePlugin

__all__ = [
    # Current names
    "PlatformCoreClient",
    "PlatformCoreConfig",
    "PlatformCorePlugin",
    "ServiceInfo",
    "TritonClient",
    "_current_scope",
    "_accumulate_inference_time",
    "SCOPE_KEY",
    "ModelResolutionMiddleware",
    # Backward-compat aliases
    "ModelManagementClient",
    "ModelManagementConfig",
    "ModelManagementPlugin",
]
