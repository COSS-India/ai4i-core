"""
Configuration system for AI4ICore Telemetry Plugin

Handles environment variables, defaults, and plugin configuration.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ai4icore_env import app_env


@dataclass
class TelemetryConfig:
    """Configuration for AI4ICore Telemetry Plugin."""

    # Core settings
    enabled: bool = True
    service_name: Optional[str] = None
    service_version: Optional[str] = None

    # Jaeger/OTLP settings
    jaeger_endpoint: Optional[str] = None

    # Instrumentation settings
    instrument_fastapi: bool = True
    instrument_httpx: bool = True
    instrument_requests: bool = False

    # IP capture middleware settings
    ip_capture_enabled: bool = True

    # Span filtering settings
    filter_http_spans: bool = True  # Filter out noisy http receive/send spans

    def __post_init__(self):
        """Initialize configuration from app_env."""
        # Core settings
        if self.service_name is None:
            self.service_name = app_env.service_name
        if self.service_version is None:
            self.service_version = app_env.service_version

        # Check if telemetry is enabled
        self.enabled = app_env.telemetry_enabled

        # Jaeger/OTLP settings
        if self.jaeger_endpoint is None:
            self.jaeger_endpoint = app_env.jaeger_endpoint or None

        # Instrumentation settings
        self.instrument_fastapi = app_env.telemetry_instrument_fastapi

        self.instrument_httpx = app_env.telemetry_instrument_httpx

        self.instrument_requests = app_env.telemetry_instrument_requests

        # IP capture middleware settings
        self.ip_capture_enabled = app_env.telemetry_ip_capture_enabled

        # Span filtering settings
        self.filter_http_spans = app_env.telemetry_filter_http_spans
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "jaeger_endpoint": self.jaeger_endpoint,
            "instrument_fastapi": self.instrument_fastapi,
            "instrument_httpx": self.instrument_httpx,
            "instrument_requests": self.instrument_requests,
            "ip_capture_enabled": self.ip_capture_enabled,
            "filter_http_spans": self.filter_http_spans,
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "TelemetryConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)
    
    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """Create configuration from environment variables."""
        return cls()
