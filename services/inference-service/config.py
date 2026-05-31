"""
Configuration for inference service.
Loads settings from environment variables and defaults.
"""

from typing import Dict, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv
import os


# Load .env file
load_dotenv()


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
    POSTGRES_HOST: str = Field("postgres", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(5432, description="PostgreSQL port")
    POSTGRES_USER: str = Field("postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field("postgres", description="PostgreSQL password")
    POSTGRES_DB: str = Field("core_db", description="PostgreSQL database name")
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

    # OpenAI-compatible LLM proxy configuration
    # Base URL for the upstream LLM server (e.g. "http://13.206.126.62:8000").
    # Routes append /v1/chat/completions or /v1/chat to this base.
    LLM_DEFAULT_ENDPOINT: str = Field("", description="Default upstream LLM base URL")
    # Optional per-model overrides as a JSON object, e.g.
    #   LLM_MODEL_ENDPOINTS='{"google/gemma-4-E4B-it":"http://10.0.0.5:8000"}'
    LLM_MODEL_ENDPOINTS: Dict[str, str] = Field(
        default_factory=dict, description="Per-model upstream base URL overrides"
    )
    LLM_INFERENCE_TIMEOUT: int = Field(60, description="LLM upstream HTTP timeout in seconds")

    # SmartModelRouter configuration
    SMR_SERVICE_URL: Optional[str] = Field(None, description="SmartModelRouter service URL")
    SMR_SERVICE_TIMEOUT: int = Field(30, description="SmartModelRouter timeout in seconds")

    # Telemetry/Observability
    ENABLE_TELEMETRY: bool = Field(True, description="Enable telemetry")
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(
        None, description="OpenTelemetry OTLP exporter endpoint"
    )

    class Config:
        """Pydantic config for loading from .env file."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        # Allow other libs (e.g. ai4icore_core.observability with OBSERVE_UTIL_*)
        # to read their own vars from the same .env without tripping validation.
        extra = "ignore"


# Global settings instance
settings = Settings()
