"""
Configuration system for AI4ICore Logging Plugin

Handles environment variables, defaults, and plugin configuration.
"""
import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class LoggingConfig:
    """Configuration for AI4ICore Logging Plugin."""
    
    # Core settings
    enabled: bool = True
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    environment: Optional[str] = None
    
    # Logging settings
    log_level: Optional[int] = None
    root_level: Optional[int] = None
    use_kafka: bool = False
    kafka_topic: str = "logs"
    
    # Middleware settings
    correlation_middleware_enabled: bool = True
    request_logging_middleware_enabled: bool = True
    
    # Request logging filtering
    exclude_health_logs: bool = False
    exclude_metrics_logs: bool = False
    exclude_options_logs: bool = True
    allowed_log_levels: Optional[str] = None  # Comma-separated: "DEBUG,INFO,WARNING,ERROR"
    min_log_level: Optional[str] = None  # Fallback: "INFO"
    include_4xx_logs: bool = False  # Default: skip 4xx (gateway logs them)
    
    # Correlation middleware settings
    correlation_header_name: str = "X-Correlation-ID"
    
    def __post_init__(self):
        """Initialize configuration from environment variables."""
        # Core settings
        if self.service_name is None:
            self.service_name = os.getenv("SERVICE_NAME")
        if self.service_version is None:
            self.service_version = os.getenv("SERVICE_VERSION")
        if self.environment is None:
            self.environment = os.getenv("ENVIRONMENT", os.getenv("ENV"))
        
        # Logging settings
        if self.log_level is None:
            log_level_str = os.getenv("LOG_LEVEL").upper()
            self.log_level = getattr(logging, log_level_str, logging.INFO)
        if self.root_level is None:
            root_level_str = os.getenv("ROOT_LOG_LEVEL")
            if root_level_str:
                self.root_level = getattr(logging, root_level_str.upper(), logging.WARNING)
            else:
                self.root_level = logging.WARNING
        
        use_kafka_env = os.getenv("USE_KAFKA_LOGGING")
        self.use_kafka = use_kafka_env.lower() in ("true", "1", "yes", "on")
        
        self.kafka_topic = os.getenv("KAFKA_LOG_TOPIC", self.kafka_topic)
        
        # Middleware settings
        enabled_env = os.getenv("LOGGING_PLUGIN_ENABLED")
        if enabled_env is not None:
            self.enabled = enabled_env.lower() in ("true", "1", "yes", "on")
        
        correlation_enabled_env = os.getenv("CORRELATION_MIDDLEWARE_ENABLED")
        if correlation_enabled_env is not None:
            self.correlation_middleware_enabled = correlation_enabled_env.lower() in ("true", "1", "yes", "on")
        
        request_logging_enabled_env = os.getenv("REQUEST_LOGGING_MIDDLEWARE_ENABLED")
        if request_logging_enabled_env is not None:
            self.request_logging_middleware_enabled = request_logging_enabled_env.lower() in ("true", "1", "yes", "on")
        
        # Request logging filtering
        exclude_health_env = os.getenv("EXCLUDE_HEALTH_LOGS")
        self.exclude_health_logs = exclude_health_env.lower() in ("true", "1", "yes", "on")
        
        exclude_metrics_env = os.getenv("EXCLUDE_METRICS_LOGS")
        self.exclude_metrics_logs = exclude_metrics_env.lower() in ("true", "1", "yes", "on")
        
        exclude_options_env = os.getenv("EXCLUDE_OPTIONS_LOGS")
        self.exclude_options_logs = exclude_options_env.lower() in ("true", "1", "yes", "on")
        
        if self.allowed_log_levels is None:
            self.allowed_log_levels = os.getenv("ALLOWED_LOG_LEVELS")
        
        if self.min_log_level is None:
            self.min_log_level = os.getenv("MIN_LOG_LEVEL")
        
        include_4xx_env = os.getenv("INCLUDE_4XX_LOGS")
        self.include_4xx_logs = include_4xx_env.lower() in ("true", "1", "yes", "on")
        
        # Correlation middleware settings
        self.correlation_header_name = os.getenv("CORRELATION_HEADER_NAME", self.correlation_header_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "log_level": self.log_level,
            "root_level": self.root_level,
            "use_kafka": self.use_kafka,
            "kafka_topic": self.kafka_topic,
            "correlation_middleware_enabled": self.correlation_middleware_enabled,
            "request_logging_middleware_enabled": self.request_logging_middleware_enabled,
            "exclude_health_logs": self.exclude_health_logs,
            "exclude_metrics_logs": self.exclude_metrics_logs,
            "exclude_options_logs": self.exclude_options_logs,
            "allowed_log_levels": self.allowed_log_levels,
            "min_log_level": self.min_log_level,
            "include_4xx_logs": self.include_4xx_logs,
            "correlation_header_name": self.correlation_header_name,
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "LoggingConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)
    
    @classmethod
    def from_env(cls) -> "LoggingConfig":
        """Create configuration from environment variables."""
        return cls()
