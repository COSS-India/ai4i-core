"""
Core Service configuration.

Consolidates settings from previously separate services (model-management,
and future feature domains) into a single enterprise-grade settings model.

All env vars use UPPER_SNAKE_CASE; pydantic-settings is case-insensitive so
both .env and OS-level vars are accepted.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Core-service configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ──
    service_name: str = "core-service"
    service_version: str = "1.0.0"
    api_version: str = "v1"
    environment: str = "development"
    debug: bool = False

    # ── Database (single primary DB) ──
    database_url: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai4iplatform_core"

    # Backwards-compatible aliases (model-management-service used APP_DB_*)
    app_db_user: Optional[str] = None
    app_db_password: Optional[str] = None
    app_db_host: Optional[str] = None
    app_db_port: Optional[int] = None
    app_db_name: Optional[str] = None
    core_db_name: Optional[str] = None

    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Redis ──
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_timeout: int = 10
    # Cache TTLs
    model_cache_ttl_seconds: int = 3600
    service_cache_ttl_seconds: int = 3600

    # ── Model management business rules ──
    max_active_versions_per_model: int = 5
    allow_deprecated_model_changes: bool = True

    # ── Endpoint validation ──
    run_inference_test: bool = True
    endpoint_validation_timeout_seconds: float = 15.0
    # "lenient" = accept <500, "strict" = accept <400
    endpoint_validation_mode: str = "lenient"
    endpoint_validation_skip_tls_verify: bool = False

    # ── CORS ──
    cors_origins: str = "*"

    # ── Logging / Observability ──
    log_level: str = "INFO"
    jaeger_endpoint: Optional[str] = None
    telemetry_enabled: bool = True

    # ── Derived helpers ──

    def get_database_url(self) -> str:
        """Build a postgres+asyncpg URL from individual fields if no full URL provided."""
        if self.database_url:
            return self.database_url
        user = self.app_db_user or self.postgres_user or "postgres"
        password = self.app_db_password or self.postgres_password or ""
        host = self.app_db_host or self.postgres_host
        port = self.app_db_port or self.postgres_port
        db = self.core_db_name or self.app_db_name or self.postgres_db
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = CoreSettings()
