"""
Configuration for AI4ICore Observability Plugin.

Env vars are bound via env_prefix=OBSERVE_UTIL_ (e.g. OBSERVE_UTIL_ENABLED).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class PluginConfig(BaseSettings):
    """Configuration for AI4ICore Observability Plugin."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="OBSERVE_UTIL_",
    )

    enabled: bool = False
    debug: bool = False
    metrics_path: str = "/enterprise/metrics"
