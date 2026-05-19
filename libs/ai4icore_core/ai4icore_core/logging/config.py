"""
Logging configuration — reads from environment variables or .env file.

Environment variables:
  SERVICE_NAME          Service identifier (appears in every log line)
  SERVICE_VERSION       Service version string (default: 1.0.0)
  ENVIRONMENT           deployment environment, e.g. production (default: development)
  LOG_LEVEL             Root log level: DEBUG | INFO | WARNING | ERROR (default: INFO)
  EXCLUDE_HEALTH_LOGS   Skip logging /health requests (default: false)
  EXCLUDE_METRICS_LOGS  Skip logging /metrics requests (default: false)
  EXCLUDE_OPTIONS_LOGS  Skip logging OPTIONS pre-flight requests (default: true)
"""

import logging
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = ""
    service_version: str = "1.0.0"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV", "environment"),
    )
    log_level_raw: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level_raw"),
    )

    exclude_health_logs: bool = False
    exclude_metrics_logs: bool = False
    exclude_options_logs: bool = True

    @property
    def log_level(self) -> int:
        return getattr(logging, self.log_level_raw.upper(), logging.INFO)


_default_config: Optional[LoggingConfig] = None


def get_default_config() -> LoggingConfig:
    global _default_config
    if _default_config is None:
        _default_config = LoggingConfig()
    return _default_config
