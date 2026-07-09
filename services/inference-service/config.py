"""
Configuration for inference service.
Loads settings from environment variables and defaults.
"""

from typing import Dict, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv


# Load .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service configuration
    SERVICE_NAME: str = Field("inference-service", description="Service name")
    SERVICE_VERSION: str = Field("1.0.1", description="Service version reported in traces")
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
    # Base URL for the upstream LLM server (e.g. "http://13.206.126.62:8000").
    # Routes append /v1/chat/completions or /v1/chat to this base.
    LLM_DEFAULT_ENDPOINT: str = Field("", description="Default upstream LLM base URL")
    # Optional per-model overrides as a JSON object, e.g.
    #   LLM_MODEL_ENDPOINTS='{"google/gemma-4-E4B-it":"http://10.0.0.5:8000"}'
    LLM_MODEL_ENDPOINTS: Dict[str, str] = Field(
        default_factory=dict, description="Per-model upstream base URL overrides"
    )
    LLM_INFERENCE_TIMEOUT: int = Field(60, description="LLM upstream HTTP timeout in seconds")

    # Per-block phase timing — on by default. When true, each request's root
    # span gains per-stage *_ms fields (resolve, validate, preprocess,
    # build_payload, triton, output_convert, output_tokens, postprocess) and a
    # human-readable "TIMING ..." log line is emitted per request. The fields
    # ride the existing request span (no new spans). Flip to false to silence.
    PHASE_TIMING_ENABLED: bool = Field(
        True, description="Emit per-stage *_ms timings + a TIMING log line per request"
    )

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
