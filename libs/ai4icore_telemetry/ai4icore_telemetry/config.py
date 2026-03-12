"""
Configuration system for AI4ICore Telemetry Plugin

Handles environment variables, defaults, and plugin configuration.
"""
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass


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
        """Initialize configuration from environment variables."""
        # Core settings - read from environment, no hardcoded defaults
        if self.service_name is None:
            self.service_name = os.getenv("SERVICE_NAME")
        if self.service_version is None:
            self.service_version = os.getenv("SERVICE_VERSION")
        
        # Check if telemetry is enabled
        enabled_env = os.getenv("TELEMETRY_ENABLED")
        if enabled_env is not None:
            self.enabled = enabled_env.lower() in ("true", "1", "yes", "on")
        
        # Jaeger/OTLP settings - read from environment, no hardcoded defaults
        if self.jaeger_endpoint is None:
            self.jaeger_endpoint = os.getenv("JAEGER_ENDPOINT")
        
        # Instrumentation settings
        instrument_fastapi_env = os.getenv("TELEMETRY_INSTRUMENT_FASTAPI")
        if instrument_fastapi_env is not None:
            self.instrument_fastapi = instrument_fastapi_env.lower() in ("true", "1", "yes", "on")
        
        instrument_httpx_env = os.getenv("TELEMETRY_INSTRUMENT_HTTPX")
        if instrument_httpx_env is not None:
            self.instrument_httpx = instrument_httpx_env.lower() in ("true", "1", "yes", "on")
        
        instrument_requests_env = os.getenv("TELEMETRY_INSTRUMENT_REQUESTS")
        if instrument_requests_env is not None:
            self.instrument_requests = instrument_requests_env.lower() in ("true", "1", "yes", "on")
        
        # IP capture middleware settings
        ip_capture_env = os.getenv("TELEMETRY_IP_CAPTURE_ENABLED")
        if ip_capture_env is not None:
            self.ip_capture_enabled = ip_capture_env.lower() in ("true", "1", "yes", "on")
        
        # Span filtering settings
        filter_http_spans_env = os.getenv("TELEMETRY_FILTER_HTTP_SPANS")
        if filter_http_spans_env is not None:
            self.filter_http_spans = filter_http_spans_env.lower() in ("true", "1", "yes", "on")
    
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
