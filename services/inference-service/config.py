"""
Configuration for inference service.
Loads settings from environment variables and defaults.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service configuration
    SERVICE_NAME: str = Field("inference-service", description="Service name")
    HOST: str = Field("0.0.0.0", description="Host to bind to")
    PORT: int = Field(8080, description="Port to bind to")
    WORKERS: int = Field(4, description="Number of worker processes")
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    DEBUG: bool = Field(False, description="Debug mode")

    # API configuration
    API_PREFIX: str = Field("/api/v1", description="API prefix for routes")
    API_TITLE: str = Field("Inference Service", description="API title")
    API_DESCRIPTION: str = Field(
        "Unified inference endpoint for all task services", description="API description"
    )

    # Database configuration
    DATABASE_URL: Optional[str] = Field(None, description="Database connection URL")
    DATABASE_POOL_SIZE: int = Field(10, description="Database connection pool size")
    DATABASE_ECHO: bool = Field(False, description="Echo SQL statements")

    # Redis configuration
    REDIS_URL: Optional[str] = Field(None, description="Redis connection URL")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password")
    CACHE_TTL_SECONDS: int = Field(300, description="Cache TTL in seconds")

    # Model Management Service
    MODEL_MANAGEMENT_SERVICE_URL: Optional[str] = Field(
        None, description="Model management service URL"
    )
    MODEL_MANAGEMENT_SERVICE_TIMEOUT: int = Field(
        30, description="Model management service timeout in seconds"
    )

    # Triton configuration
    DEFAULT_TRITON_TIMEOUT: int = Field(60, description="Default Triton timeout in seconds")

    # SmartModelRouter configuration
    SMR_SERVICE_URL: Optional[str] = Field(None, description="SmartModelRouter service URL")
    SMR_SERVICE_TIMEOUT: int = Field(30, description="SmartModelRouter timeout in seconds")

    # Telemetry/Observability
    ENABLE_TELEMETRY: bool = Field(True, description="Enable telemetry")
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(
        None, description="OpenTelemetry OTLP exporter endpoint"
    )

    class Config:
        """Pydantic config."""

        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

