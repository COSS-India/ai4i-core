"""
Configuration system for AI4ICore Logging Plugin

Handles environment variables, defaults, and plugin configuration.
"""
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ai4icore_env import app_env


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
            self.service_name = app_env.service_name
        if self.service_version is None:
            self.service_version = app_env.service_version
        if self.environment is None:
            self.environment = app_env.environment or app_env.env

        # Logging settings
        if self.log_level is None:
            log_level_str = app_env.log_level.upper()
            self.log_level = getattr(logging, log_level_str, logging.INFO)
        if self.root_level is None:
            root_level_str = app_env.root_log_level
            if root_level_str:
                self.root_level = getattr(logging, root_level_str.upper(), logging.WARNING)
            else:
                self.root_level = logging.WARNING

        self.use_kafka = app_env.use_kafka_logging

        self.kafka_topic = app_env.kafka_log_topic or self.kafka_topic

        # Middleware settings
        self.enabled = app_env.logging_plugin_enabled

        self.correlation_middleware_enabled = app_env.correlation_middleware_enabled

        self.request_logging_middleware_enabled = app_env.request_logging_middleware_enabled

        # Request logging filtering
        self.exclude_health_logs = app_env.exclude_health_logs

        self.exclude_metrics_logs = app_env.exclude_metrics_logs

        self.exclude_options_logs = app_env.exclude_options_logs

        if self.allowed_log_levels is None:
            self.allowed_log_levels = app_env.allowed_log_levels

        if self.min_log_level is None:
            self.min_log_level = app_env.min_log_level

        self.include_4xx_logs = app_env.include_4xx_logs

        # Correlation middleware settings
        self.correlation_header_name = app_env.correlation_header_name or self.correlation_header_name
    
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
