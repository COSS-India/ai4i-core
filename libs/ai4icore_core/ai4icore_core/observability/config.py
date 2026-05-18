"""
Configuration system for AI4ICore Observability Plugin

Reads its own environment variables via pydantic-settings — no dependency
on ai4icore_core.env.

Env var naming preserved: all fields are bound to ``OBSERVE_UTIL_*``
env vars (matching the historical schema in ``.env`` files), via the
``env_prefix`` config option.
"""
from typing import Any, Dict

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

    # Core
    enabled: bool = False
    debug: bool = False

    # Endpoints
    metrics_path: str = "/enterprise/metrics"
    health_path: str = "/enterprise/health"

    # Monitoring toggles
    collect_system_metrics: bool = True
    collect_gpu_metrics: bool = False
    collect_db_metrics: bool = False

    # SLA targets
    availability_target: float = 99.9
    response_time_target: float = 1.0
    throughput_target: float = 100.0

    # Advanced
    max_completed_requests: int = 1000
    metrics_update_interval: int = 60
    system_metrics_interval: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "debug": self.debug,
            "metrics_path": self.metrics_path,
            "health_path": self.health_path,
            "collect_system_metrics": self.collect_system_metrics,
            "collect_gpu_metrics": self.collect_gpu_metrics,
            "collect_db_metrics": self.collect_db_metrics,
            "availability_target": self.availability_target,
            "response_time_target": self.response_time_target,
            "throughput_target": self.throughput_target,
            "max_completed_requests": self.max_completed_requests,
            "metrics_update_interval": self.metrics_update_interval,
            "system_metrics_interval": self.system_metrics_interval,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "PluginConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)

    @classmethod
    def from_env(cls) -> "PluginConfig":
        """Create configuration from environment variables."""
        return cls()
