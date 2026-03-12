"""
Model Management Configuration
Configuration class for Model Management plugin
"""

from typing import Optional
from pydantic import BaseModel, Field

from ai4icore_env import app_env


class ModelManagementConfig(BaseModel):
    """Configuration for Model Management plugin"""

    # Model Management Service settings
    model_management_service_url: str = Field(
        default_factory=lambda: app_env.model_management_service_url,
        description="Base URL of Model Management Service"
    )

    model_management_api_key: Optional[str] = Field(
        default_factory=lambda: app_env.model_management_service_api_key,
        description="API key for Model Management Service (optional, fallback)"
    )

    # Cache settings
    cache_ttl_seconds: int = Field(
        default_factory=lambda: app_env.model_management_cache_ttl,
        description="Cache TTL in seconds (default: 300 = 5 minutes)"
    )

    triton_endpoint_cache_ttl: int = Field(
        default_factory=lambda: app_env.triton_endpoint_cache_ttl,
        description="Triton endpoint cache TTL in seconds"
    )

    # Default Triton settings (fallback)
    default_triton_endpoint: Optional[str] = Field(
        default_factory=lambda: app_env.triton_endpoint,
        description="Default Triton endpoint (fallback if Model Management unavailable)"
    )

    default_triton_api_key: Optional[str] = Field(
        default_factory=lambda: app_env.triton_api_key or None,
        description="Default Triton API key"
    )

    # HTTP client settings
    request_timeout: float = Field(
        default=10.0,
        description="HTTP request timeout in seconds"
    )

    # Middleware settings
    middleware_enabled: bool = Field(
        default=True,
        description="Enable Model Resolution Middleware"
    )

    middleware_paths: list[str] = Field(
        default_factory=lambda: ["/api/v1"],
        description="URL paths where middleware should run (prefix matching)"
    )

    @classmethod
    def from_env(cls) -> "ModelManagementConfig":
        """Create config from environment variables"""
        return cls()

