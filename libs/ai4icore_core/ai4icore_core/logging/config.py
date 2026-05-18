"""
Configuration system for AI4ICore Logging Plugin

Reads its own environment variables via pydantic-settings — no dependency
on ai4icore_core.env. All historical env var names are preserved.
"""
import logging
from typing import Any, Dict, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _level_from_str(s: Optional[str], default: int) -> int:
    """Convert a string log level (e.g. 'INFO') to logging.<LEVEL>, with a default."""
    if not s:
        return default
    return getattr(logging, s.upper(), default)


class LoggingConfig(BaseSettings):
    """Configuration for AI4ICore Logging Plugin."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity (shared env vars; no prefix) ──
    service_name: str = ""
    service_version: str = "1.0.0"
    environment: str = Field(default="development", validation_alias=AliasChoices("ENVIRONMENT", "ENV", "environment"))

    # ── Master toggle ──
    enabled: bool = Field(default=True, validation_alias=AliasChoices("LOGGING_PLUGIN_ENABLED", "enabled"))

    # ── Log level (raw string from env; resolved property below) ──
    log_level_raw: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL", "log_level_raw"))
    root_log_level_raw: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("ROOT_LOG_LEVEL", "root_log_level_raw")
    )

    # ── Kafka shipping ──
    use_kafka: bool = Field(default=False, validation_alias=AliasChoices("USE_KAFKA_LOGGING", "use_kafka"))
    kafka_topic: str = Field(default="logs", validation_alias=AliasChoices("KAFKA_LOG_TOPIC", "kafka_topic"))
    kafka_bootstrap_servers: str = ""

    # ── Middleware toggles ──
    correlation_middleware_enabled: bool = True
    request_logging_middleware_enabled: bool = True

    # ── Request-logging filtering ──
    exclude_health_logs: bool = False
    exclude_metrics_logs: bool = False
    exclude_options_logs: bool = True
    allowed_log_levels: str = ""
    min_log_level: str = "INFO"
    include_4xx_logs: bool = False

    # ── Correlation middleware ──
    correlation_header_name: str = "X-Correlation-ID"

    # ── Service-to-service request logging ──
    request_log_include_paths: str = ""

    # ---- Derived properties ----

    @property
    def log_level(self) -> int:
        return _level_from_str(self.log_level_raw, logging.INFO)

    @property
    def root_level(self) -> int:
        return _level_from_str(self.root_log_level_raw, logging.WARNING)

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


# Lazy module-level singleton — used by formatters/handlers/middleware that
# need a config but aren't passed one explicitly. We instantiate lazily so
# that env vars set after import time (e.g. in tests) still take effect.
_default_config: Optional[LoggingConfig] = None


def get_default_config() -> LoggingConfig:
    """Return the cached default LoggingConfig, instantiating on first call."""
    global _default_config
    if _default_config is None:
        _default_config = LoggingConfig()
    return _default_config
