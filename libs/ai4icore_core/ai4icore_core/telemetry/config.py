"""
Configuration system for AI4ICore Telemetry

Reads environment variables via pydantic-settings with no external dependencies.
Phase 1: Console output only
Phase 2: Kafka endpoint config will be added here
"""
from typing import Any, Dict, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseSettings):
    """Configuration for AI4ICore Telemetry."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core service identity ──
    service_name: str = ""
    service_version: str = "1.0.0"

    # ── Master switch ──
    enabled: bool = Field(default=True, validation_alias=AliasChoices("TELEMETRY_ENABLED", "enabled"))

    # ── Optional instrumentation (for future use) ──
    # ❌ REMOVED: jaeger_endpoint - no longer using Jaeger
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

    # ── IP capture (optional, Phase 1) ──
    ip_capture_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("TELEMETRY_IP_CAPTURE_ENABLED", "ip_capture_enabled")
    )

    # ── Phase 2: Kafka and OpenSearch config will be added here ──
    # ❌ REMOVED: jaeger_endpoint - no longer using Jaeger
    # ❌ REMOVED: jaeger_query_url - no longer using Jaeger
    # ❌ REMOVED: jaeger_query_base_path - no longer using Jaeger
    # ❌ REMOVED: opensearch_url, opensearch_username, opensearch_password - Phase 2
    # ❌ REMOVED: filter_http_spans - FilteringSpanExporter removed

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary.

        ✅ JUSTIFICATION:
        - Only includes Phase 1 fields (core + instrumentation)
        - Jaeger/OpenSearch fields removed (will be re-added in Phase 2)
        """
        return {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "instrument_fastapi": self.instrument_fastapi,
            "instrument_httpx": self.instrument_httpx,
            "instrument_requests": self.instrument_requests,
            "ip_capture_enabled": self.ip_capture_enabled,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "TelemetryConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)

    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """Create configuration from environment variables."""
        return cls()


# Lazy module-level singleton — same pattern as LoggingConfig.get_default_config()
_default_config: Optional["TelemetryConfig"] = None


def get_default_config() -> "TelemetryConfig":
    """Return the cached default TelemetryConfig, instantiating on first call.

    ✅ JUSTIFICATION: Singleton pattern ensures config is loaded once and reused
    """
    global _default_config
    if _default_config is None:
        _default_config = TelemetryConfig()
    return _default_config
