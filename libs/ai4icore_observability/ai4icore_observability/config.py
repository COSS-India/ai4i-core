"""
Configuration system for AI4ICore Observability Plugin

Handles environment variables, defaults, and plugin configuration.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ai4icore_env import app_env


@dataclass
class PluginConfig:
    """Configuration for AI4ICore Observability Plugin."""

    # Core settings
    enabled: bool = False
    debug: bool = False

    # Endpoint settings
    metrics_path: str = "/enterprise/metrics"
    health_path: str = "/enterprise/health"

    # Monitoring settings
    collect_system_metrics: bool = True
    collect_gpu_metrics: bool = True
    collect_db_metrics: bool = True

    # SLA settings
    availability_target: float = 100.0
    response_time_target: float = 1.0
    throughput_target: float = 20.0

    # Advanced settings
    max_completed_requests: int = 1000
    metrics_update_interval: int = 10
    system_metrics_interval: int = 5
    # Customer / app defaults
    customers: list = None
    apps: list = None

    def __post_init__(self):
        """Initialize configuration from app_env."""
        self.enabled = app_env.observe_util_enabled
        self.debug = app_env.observe_util_debug

        self.metrics_path = app_env.observe_util_metrics_path or self.metrics_path
        self.health_path = app_env.observe_util_health_path or self.health_path

        self.collect_system_metrics = app_env.observe_util_collect_system_metrics
        self.collect_gpu_metrics = app_env.observe_util_collect_gpu_metrics
        self.collect_db_metrics = app_env.observe_util_collect_db_metrics

        # SLA targets
        self.availability_target = app_env.observe_util_availability_target
        self.response_time_target = app_env.observe_util_response_time_target
        self.throughput_target = app_env.observe_util_throughput_target

        # Advanced settings
        self.max_completed_requests = app_env.observe_util_max_completed_requests
        self.metrics_update_interval = app_env.observe_util_metrics_update_interval
        self.system_metrics_interval = app_env.observe_util_system_metrics_interval

        # Defaults for customers/apps
        if self.customers is None:
            customers_env = app_env.observe_util_customers
            self.customers = [c.strip() for c in customers_env.split(",") if c.strip()] if customers_env else []
        if self.apps is None:
            apps_env = app_env.observe_util_apps
            self.apps = [a.strip() for a in apps_env.split(",") if a.strip()] if apps_env else []
    
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
            "customers": self.customers,
            "apps": self.apps,
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "PluginConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)
    
    @classmethod
    def from_env(cls) -> "PluginConfig":
        """Create configuration from environment variables."""
        return cls()


# Global configuration instance
config = PluginConfig.from_env()

