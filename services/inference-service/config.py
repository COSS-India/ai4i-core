"""
Configuration for inference service.
Loads settings from environment variables and defaults.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv


# Load .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service configuration
    SERVICE_NAME: str = Field("inference-service", description="Service name")
    SERVICE_VERSION: str = Field("release-2.6", description="Service version reported in traces")
    HOST: str = Field("0.0.0.0", description="Host to bind to")
    # Default matches the Dockerfile EXPOSE/HEALTHCHECK port — a container
    # started without PORT set must still pass its health check.
    PORT: int = Field(8090, description="Port to bind to")
    # Scale via k8s replicas rather than in-pod workers; >1 also requires
    # prometheus_client multiprocess mode for consistent /metrics.
    WORKERS: int = Field(1, description="Number of worker processes")
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    DEBUG: bool = Field(False, description="Debug mode")
    ENABLE_DOCS: bool = Field(
        True, description="Expose /docs and /openapi.json (disable in production)"
    )
    CORS_ALLOW_ORIGINS: str = Field(
        "*", description="Comma-separated list of allowed CORS origins"
    )

    # API configuration
    API_PREFIX: str = Field("/api/v1", description="API prefix for routes")

    # Resolver cache
    CACHE_TTL_SECONDS: int = Field(
        300, description="In-memory service-resolution cache TTL in seconds"
    )

    # Redis — read-only, and only for the inference-type catalogue
    # (core:inference_type:*, written by platform-core). Must point at the same
    # host AND logical DB as platform-core or the keys will not be found; both
    # default to DB 0. The catalogue falls back to platform-core over HTTP and
    # then to a stale snapshot, so an unset or unreachable Redis degrades the
    # billing-unit label rather than breaking inference.
    REDIS_HOST: str = Field("localhost", description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password")
    REDIS_DB: int = Field(0, description="Redis logical DB; must match platform-core")
    REDIS_TIMEOUT: int = Field(10, description="Redis socket timeout in seconds")

    # Model Management Service
    MODEL_MANAGEMENT_SERVICE_URL: Optional[str] = Field(
        None, description="Model management service URL"
    )
    MODEL_MANAGEMENT_SERVICE_TIMEOUT: int = Field(
        30, description="Model management service timeout in seconds"
    )

    # Triton configuration
    DEFAULT_TRITON_TIMEOUT: int = Field(300, description="Triton inference HTTP timeout in seconds")

    # OpenAI-compatible LLM proxy configuration
    # Endpoint resolution is handled via MMS (model management service) using
    # the serviceId from the request payload — no static endpoint config needed.
    LLM_INFERENCE_TIMEOUT: int = Field(60, description="LLM upstream HTTP timeout in seconds")

    # Telemetry/Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(
        None, description="OpenTelemetry OTLP exporter endpoint"
    )
    # Off by default — only the logging/streaming compose profiles bring Kafka
    # up. When false, traces are not exported (spans never written to stdout).
    # Never imports kafka-python when false, avoiding the bootstrap retry storm
    # on services without a broker. Flip to true in services/inference-service/.env
    # when running `--profile logging` or `--profile streaming`.
    KAFKA_ENABLED: bool = Field(False, description="Ship OTel trace spans to Kafka")
    KAFKA_SERVER: str = Field(
        "localhost:9092", description="Kafka bootstrap servers for trace export"
    )
    KAFKA_TOPIC_OTEL_TRACE: str = Field(
        "kafka-topic-otel-trace", description="Kafka topic for OTel trace spans"
    )

    # Security — user-supplied audio/image URI downloads (SSRF guard)
    ALLOW_PRIVATE_DOWNLOAD_HOSTS: bool = Field(
        False,
        description="Allow audio/image URI downloads from private/loopback addresses "
        "(enable only for local development)",
    )

    class Config:
        """Pydantic config for loading from .env file."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        # Allow other libs (e.g. ai4i_core.observability with OBSERVE_UTIL_*)
        # to read their own vars from the same .env without tripping validation.
        extra = "ignore"


# Global settings instance
settings = Settings()
