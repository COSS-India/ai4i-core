"""
Main Logging Plugin for AI4ICore platform

Provides structured JSON logging with trace correlation for AI4ICore services.
Follows the same plugin pattern as ObservabilityPlugin and ModelManagementPlugin.
"""
from typing import Optional, Dict, Any
from fastapi import FastAPI

from .config import LoggingConfig
from .logger import configure_logging
from .middleware import CorrelationMiddleware
from .service_request_logging import ServiceRequestLoggingMiddleware


class LoggingPlugin:
    """Main plugin class for AI4ICore Logging."""
    
    def __init__(self, config: Optional[LoggingConfig] = None):
        """
        Initialize the logging plugin.
        
        Args:
            config: LoggingConfig instance. If None, creates one from environment variables.
        """
        self.config = config or LoggingConfig.from_env()
        self._initialized = False
    
    def register_middleware(self, app: FastAPI) -> None:
        """
        Register middleware with FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        if not self.config.enabled:
            return
        
        # Add CorrelationMiddleware (extracts X-Correlation-ID from headers)
        if self.config.correlation_middleware_enabled:
            app.add_middleware(
                CorrelationMiddleware,
                header_name=self.config.correlation_header_name
            )
        
        # Add ServiceRequestLoggingMiddleware (logs request/response with structured JSON)
        if self.config.request_logging_middleware_enabled:
            app.add_middleware(
                ServiceRequestLoggingMiddleware,
                include_4xx=self.config.include_4xx_logs
            )
    
    def register_plugin(self, app: FastAPI) -> None:
        """
        Register the complete plugin with FastAPI application.
        
        This method:
        1. Configures root logging (configure_logging)
        2. Registers middleware (CorrelationMiddleware, ServiceRequestLoggingMiddleware)
        
        Args:
            app: FastAPI application instance
        """
        if not self.config.enabled:
            return
        
        # Step 1: Configure root logging
        configure_logging(
            service_name=self.config.service_name,
            level=self.config.log_level,
            use_kafka=self.config.use_kafka,
            kafka_topic=self.config.kafka_topic,
            root_level=self.config.root_level,
        )
        
        # Step 2: Register middleware
        self.register_middleware(app)
        
        self._initialized = True
    
    def get_config(self) -> LoggingConfig:
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
        self.config = LoggingConfig.from_dict(new_config)
    
    def get_status(self) -> Dict[str, Any]:
        """Get plugin status information."""
        return {
            "initialized": self._initialized,
            "enabled": self.config.enabled,
            "service_name": self.config.service_name,
            "service_version": self.config.service_version,
            "environment": self.config.environment,
            "use_kafka": self.config.use_kafka,
            "correlation_middleware_enabled": self.config.correlation_middleware_enabled,
            "request_logging_middleware_enabled": self.config.request_logging_middleware_enabled,
        }


# Convenience functions for easy integration
def create_logging_plugin(config: Optional[LoggingConfig] = None) -> LoggingPlugin:
    """
    Create and return a LoggingPlugin instance.
    
    Args:
        config: Optional LoggingConfig instance. If None, creates from environment variables.
        
    Returns:
        LoggingPlugin instance
        
    Example:
        plugin = create_logging_plugin()
        plugin.register_plugin(app)
    """
    return LoggingPlugin(config)


def register_logging_plugin(app: FastAPI, config: Optional[LoggingConfig] = None) -> LoggingPlugin:
    """
    Create and register logging plugin with FastAPI app in one call.
    
    Args:
        app: FastAPI application instance
        config: Optional LoggingConfig instance. If None, creates from environment variables.
        
    Returns:
        LoggingPlugin instance
        
    Example:
        plugin = register_logging_plugin(app)
        # Plugin is now registered and middleware is added
    """
    plugin = LoggingPlugin(config)
    plugin.register_plugin(app)
    return plugin
