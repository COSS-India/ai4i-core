"""
Main Telemetry Plugin for AI4ICore platform

Provides distributed tracing with OpenTelemetry and Jaeger integration.
Follows the standard plugin pattern consistent with other AI4ICore modules.
"""
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI

from .config import TelemetryConfig
from .tracing import setup_tracing, get_tracer, TRACING_AVAILABLE
from .ip_middleware import IPCaptureMiddleware

logger = logging.getLogger(__name__)


class TelemetryPlugin:
    """Main plugin class for AI4ICore Telemetry."""
    
    def __init__(self, config: Optional[TelemetryConfig] = None):
        """
        Initialize the telemetry plugin.
        
        Args:
            config: TelemetryConfig instance. If None, creates one from environment variables.
        """
        self.config = config or TelemetryConfig.from_env()
        self._initialized = False
        self._tracer = None
    
    def register_middleware(self, app: FastAPI) -> None:
        """
        Register middleware with FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        if not self.config.enabled:
            return
        
        if not TRACING_AVAILABLE:
            logger.warning("OpenTelemetry not available, telemetry middleware disabled")
            return
        
        # Add IP capture middleware if enabled
        if self.config.ip_capture_enabled:
            app.add_middleware(IPCaptureMiddleware)
            logger.debug("IP capture middleware registered")
    
    def register_instrumentation(self) -> None:
        """
        Register OpenTelemetry instrumentation for FastAPI, HTTPX, and requests.
        
        This should be called after setup_tracing() to ensure the tracer provider is configured.
        """
        if not self.config.enabled:
            return
        
        if not TRACING_AVAILABLE:
            return
        
        try:
            # FastAPI instrumentation
            if self.config.instrument_fastapi:
                try:
                    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                    # Note: FastAPIInstrumentor.instrument_app() should be called separately
                    # after the app is created, so we just mark it as available here
                    logger.debug("FastAPI instrumentation available")
                except ImportError:
                    logger.warning("FastAPI instrumentation not available")
            
            # HTTPX instrumentation
            if self.config.instrument_httpx:
                try:
                    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
                    HTTPXClientInstrumentor().instrument()
                    logger.debug("HTTPX instrumentation registered")
                except ImportError:
                    logger.warning("HTTPX instrumentation not available")
            
            # Requests instrumentation
            if self.config.instrument_requests:
                try:
                    from opentelemetry.instrumentation.requests import RequestsInstrumentor
                    RequestsInstrumentor().instrument()
                    logger.debug("Requests instrumentation registered")
                except ImportError:
                    logger.warning("Requests instrumentation not available")
        except Exception as e:
            logger.error(f"Failed to register instrumentation: {e}")
    
    def register_plugin(self, app: FastAPI, **kwargs) -> None:
        """
        Register the complete plugin with FastAPI application.
        
        This method:
        1. Sets up OpenTelemetry tracing
        2. Registers instrumentation (HTTPX, requests)
        3. Registers middleware (IP capture)
        4. Instruments FastAPI app
        
        Args:
            app: FastAPI application instance
            **kwargs: Additional arguments (e.g., instrument_app=True to instrument FastAPI)
        """
        if not self.config.enabled:
            logger.info("Telemetry plugin is disabled")
            return
        
        if not TRACING_AVAILABLE:
            logger.warning("OpenTelemetry not available, telemetry plugin disabled")
            return
        
        # Validate required configuration
        if not self.config.service_name:
            logger.error("SERVICE_NAME environment variable is required for telemetry plugin")
            return
        
        try:
            # Step 1: Setup tracing
            self._tracer = setup_tracing(
                service_name=self.config.service_name,
                jaeger_endpoint=self.config.jaeger_endpoint
            )
            
            if self._tracer is None:
                logger.warning("Failed to setup tracing, telemetry plugin disabled")
                return
            
            # Step 2: Register instrumentation (HTTPX, requests)
            self.register_instrumentation()
            
            # Step 3: Register middleware
            self.register_middleware(app)
            
            # Step 4: Instrument FastAPI app if requested
            instrument_app = kwargs.get("instrument_app", self.config.instrument_fastapi)
            if instrument_app and self.config.instrument_fastapi:
                try:
                    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                    FastAPIInstrumentor.instrument_app(app)
                    logger.debug("FastAPI app instrumented")
                except ImportError:
                    logger.warning("FastAPI instrumentation not available")
                except Exception as e:
                    logger.error(f"Failed to instrument FastAPI app: {e}")
            
            self._initialized = True
            logger.info(f"✅ Telemetry plugin initialized for service: {self.config.service_name}")
        
        except Exception as e:
            logger.error(f"❌ Failed to initialize telemetry plugin: {e}")
            self._initialized = False
    
    def get_tracer(self):
        """Get the tracer instance."""
        if not self._initialized:
            return None
        return self._tracer or get_tracer(self.config.service_name)
    
    def get_config(self) -> TelemetryConfig:
        """Get the configuration instance."""
        return self.config
    
    def is_initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._initialized
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update plugin configuration.
        
        Args:
            new_config: Dictionary with configuration values to update
        """
        self.config = TelemetryConfig.from_dict(new_config)
        logger.debug("Telemetry configuration updated")
    
    def get_status(self) -> Dict[str, Any]:
        """Get plugin status information."""
        return {
            "enabled": self.config.enabled,
            "initialized": self._initialized,
            "service_name": self.config.service_name,
            "service_version": self.config.service_version,
            "jaeger_endpoint": self.config.jaeger_endpoint,
            "tracing_available": TRACING_AVAILABLE,
            "tracer_initialized": self._tracer is not None,
            "instrument_fastapi": self.config.instrument_fastapi,
            "instrument_httpx": self.config.instrument_httpx,
            "instrument_requests": self.config.instrument_requests,
            "ip_capture_enabled": self.config.ip_capture_enabled,
        }
    
    async def close(self) -> None:
        """
        Cleanup resources.
        
        This method can be called during application shutdown to clean up
        any resources used by the telemetry plugin.
        """
        # OpenTelemetry SDK handles cleanup automatically
        # This method is provided for consistency with other plugins
        pass


# Convenience functions for easy integration
def create_telemetry_plugin(config: Optional[TelemetryConfig] = None) -> TelemetryPlugin:
    """
    Create and return a TelemetryPlugin instance.
    
    Args:
        config: Optional TelemetryConfig instance. If None, creates from environment variables.
        
    Returns:
        TelemetryPlugin instance
        
    Example:
        plugin = create_telemetry_plugin()
        plugin.register_plugin(app)
    """
    return TelemetryPlugin(config)


def register_telemetry_plugin(app: FastAPI, config: Optional[TelemetryConfig] = None, **kwargs) -> TelemetryPlugin:
    """
    Create and register telemetry plugin with FastAPI app in one call.
    
    Args:
        app: FastAPI application instance
        config: Optional TelemetryConfig instance. If None, creates from environment variables.
        **kwargs: Additional arguments passed to register_plugin (e.g., instrument_app=True)
        
    Returns:
        TelemetryPlugin instance
        
    Example:
        plugin = register_telemetry_plugin(app)
        # Plugin is now registered, tracing is set up, and middleware is added
    """
    plugin = TelemetryPlugin(config)
    plugin.register_plugin(app, **kwargs)
    return plugin
