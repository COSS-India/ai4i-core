"""
Platform Core Plugin
Easy integration plugin for FastAPI applications
"""

import logging
from typing import Optional

from fastapi import FastAPI

from .client import PlatformCoreClient
from .config import PlatformCoreConfig
from .middleware import ModelResolutionMiddleware

logger = logging.getLogger(__name__)


class PlatformCorePlugin:
    """Plugin for easy Platform Core integration in FastAPI apps"""

    def __init__(self, config: Optional[PlatformCoreConfig] = None):
        """
        Initialize plugin

        Args:
            config: Optional configuration (defaults to from_env())
        """
        self.config = config or PlatformCoreConfig.from_env()
        self.platform_core_client: Optional[PlatformCoreClient] = None
        self.redis_client = None

    def register_plugin(self, app: FastAPI, redis_client=None):
        """
        Register plugin with FastAPI app

        Args:
            app: FastAPI application instance
            redis_client: Optional Redis client for shared caching
        """
        # Initialize Platform Core client
        self.platform_core_client = PlatformCoreClient(
            base_url=self.config.platform_core_service_url,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
            timeout=self.config.request_timeout
        )

        # Store Redis client
        self.redis_client = redis_client

        # Store in app state for access by routes
        app.state.platform_core_client = self.platform_core_client
        app.state.redis_client = redis_client
        app.state.triton_endpoint = self.config.default_triton_endpoint
        app.state.triton_api_key = self.config.default_triton_api_key
        app.state.triton_endpoint_cache_ttl = self.config.triton_endpoint_cache_ttl

        # Add middleware if enabled
        if self.config.middleware_enabled:
            app.add_middleware(
                ModelResolutionMiddleware,
                platform_core_client=self.platform_core_client,
                redis_client=redis_client,
                app_state=app.state,
                cache_ttl_seconds=self.config.cache_ttl_seconds,
                default_triton_endpoint=self.config.default_triton_endpoint,
                default_triton_api_key=self.config.default_triton_api_key,
                enabled_paths=self.config.middleware_paths,
                config_service_url=self.config.config_service_url,
                health_gate_enabled=self.config.health_gate_enabled,
                health_gate_timeout_seconds=self.config.health_gate_timeout_seconds,
                health_gate_cache_ttl_seconds=self.config.health_gate_cache_ttl_seconds,
            )
            logger.info(
                f"✅ Model Resolution Middleware registered for paths: {self.config.middleware_paths}"
            )

            if self.config.health_gate_enabled:
                @app.on_event("shutdown")
                async def _close_health_gate_client() -> None:
                    client = getattr(app.state, "_health_gate_client", None)
                    if client is not None:
                        try:
                            await client.aclose()
                        except Exception:
                            pass
                        setattr(app.state, "_health_gate_client", None)

        logger.info(
            f"✅ Platform Core Plugin initialized: {self.config.platform_core_service_url}"
        )

    async def close(self):
        """Cleanup resources"""
        if self.platform_core_client:
            await self.platform_core_client.close()
