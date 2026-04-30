"""
Model Management Configuration
Configuration class for Model Management plugin
"""

import os
from typing import Optional
from pydantic import BaseModel, Field


class ModelManagementConfig(BaseModel):
    """Configuration for Model Management plugin"""
    
    # Model Management Service settings
    model_management_service_url: str = Field(
        default_factory=lambda: os.getenv(
            "MODEL_MANAGEMENT_SERVICE_URL",
            "http://model-management-service:8091"
        ),
        description="Base URL of Model Management Service"
    )
    
    model_management_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("MODEL_MANAGEMENT_SERVICE_API_KEY"),
        description="API key for Model Management Service (optional, fallback)"
    )
    
    # Cache settings
    cache_ttl_seconds: int = Field(
        default=int(os.getenv("MODEL_MANAGEMENT_CACHE_TTL", "300")),
        description="Cache TTL in seconds (default: 300 = 5 minutes)"
    )
    
    triton_endpoint_cache_ttl: int = Field(
        default=int(os.getenv("TRITON_ENDPOINT_CACHE_TTL", "300")),
        description="Triton endpoint cache TTL in seconds"
    )
    
    # Default Triton settings (fallback)
    default_triton_endpoint: Optional[str] = Field(
        default_factory=lambda: os.getenv("TRITON_ENDPOINT"),
        description="Default Triton endpoint (fallback if Model Management unavailable)"
    )
    
    default_triton_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("TRITON_API_KEY"),
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

