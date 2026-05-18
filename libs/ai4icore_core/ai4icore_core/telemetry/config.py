"""
Configuration system for AI4ICore Telemetry Plugin

Reads its own environment variables via pydantic-settings — no dependency
on ai4icore_core.env. Field names map 1:1 to the existing
``TELEMETRY_*`` / ``JAEGER_*`` / ``SERVICE_*`` env vars used historically.
"""
from typing import Any, Dict, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseSettings):
    """Configuration for AI4ICore Telemetry Plugin."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core (service identity reused across logging/telemetry; no prefix)
    service_name: str = ""
    service_version: str = "1.0.0"

    # Master switch
    enabled: bool = Field(default=True, validation_alias=AliasChoices("TELEMETRY_ENABLED", "enabled"))

    # Jaeger / OTLP endpoint
    jaeger_endpoint: Optional[str] = None

    # Instrumentation toggles
    instrument_fastapi: bool = Field(
        default=True, validation_alias=AliasChoices("TELEMETRY_INSTRUMENT_FASTAPI", "instrument_fastapi")
    )
    instrument_httpx: bool = Field(
        default=False, validation_alias=AliasChoices("TELEMETRY_INSTRUMENT_HTTPX", "instrument_httpx")
    )
    instrument_requests: bool = Field(
        default=False, validation_alias=AliasChoices("TELEMETRY_INSTRUMENT_REQUESTS", "instrument_requests")
    )

    # IP capture
    ip_capture_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("TELEMETRY_IP_CAPTURE_ENABLED", "ip_capture_enabled")
    )

    # Span filtering
    filter_http_spans: bool = Field(
        default=False, validation_alias=AliasChoices("TELEMETRY_FILTER_HTTP_SPANS", "filter_http_spans")
    )

    # ── Jaeger Query API (used by JaegerQueryClient) ──
    jaeger_query_url: Optional[str] = None
    jaeger_query_base_path: str = "/jaeger"

    # ── OpenSearch (used by OpenSearchQueryClient) ──
    opensearch_url: Optional[str] = None
    opensearch_username: Optional[str] = None
    opensearch_password: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "jaeger_endpoint": self.jaeger_endpoint or None,
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


# Lazy module-level singleton — used by the standalone client classes
# (JaegerQueryClient, OpenSearchQueryClient) and setup_tracing(). Same
# pattern as LoggingConfig.get_default_config().
_default_config: Optional["TelemetryConfig"] = None


def get_default_config() -> "TelemetryConfig":
    """Return the cached default TelemetryConfig, instantiating on first call."""
    global _default_config
    if _default_config is None:
        _default_config = TelemetryConfig()
    return _default_config
