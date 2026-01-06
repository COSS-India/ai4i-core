"""
Model Management Plugin
Easy integration plugin for FastAPI applications
"""

import logging
from typing import Optional

from fastapi import FastAPI

from .client import ModelManagementClient
from .config import ModelManagementConfig
from .middleware import ModelResolutionMiddleware

logger = logging.getLogger(__name__)


class ModelManagementPlugin:
    """Plugin for easy Model Management integration in FastAPI apps"""
    
    def __init__(self, config: Optional[ModelManagementConfig] = None):
        """
        Initialize plugin
        
        Args:
            config: Optional configuration (defaults to from_env())
        """
        self.config = config or ModelManagementConfig.from_env()
        self.model_management_client: Optional[ModelManagementClient] = None
        self.redis_client = None
    
    def register_plugin(self, app: FastAPI, redis_client = None):
        """
        Register plugin with FastAPI app
        
        Args:
            app: FastAPI application instance
            redis_client: Optional Redis client for shared caching
        """
        # Initialize Model Management client
        self.model_management_client = ModelManagementClient(
            base_url=self.config.model_management_service_url,
            api_key=self.config.model_management_api_key,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
            timeout=self.config.request_timeout
        )
        
        # Store Redis client
        self.redis_client = redis_client
        
        # Store in app state for access by routes
        app.state.model_management_client = self.model_management_client
        app.state.redis_client = redis_client
        app.state.triton_endpoint = self.config.default_triton_endpoint
        app.state.triton_api_key = self.config.default_triton_api_key
        app.state.triton_endpoint_cache_ttl = self.config.triton_endpoint_cache_ttl
        
        # Add middleware if enabled
        if self.config.middleware_enabled:
            app.add_middleware(
                ModelResolutionMiddleware,
                model_management_client=self.model_management_client,
                redis_client=redis_client,
                cache_ttl_seconds=self.config.cache_ttl_seconds,
                default_triton_endpoint=self.config.default_triton_endpoint,
                default_triton_api_key=self.config.default_triton_api_key,
                enabled_paths=self.config.middleware_paths
            )
            logger.info(
                f"✅ Model Resolution Middleware registered for paths: {self.config.middleware_paths}"
            )
        
        logger.info(
            f"✅ Model Management Plugin initialized: {self.config.model_management_service_url}"
        )
    
    async def close(self):
        """Cleanup resources"""
        if self.model_management_client:
            await self.model_management_client.close()

