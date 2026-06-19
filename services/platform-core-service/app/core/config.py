"""
Core Service configuration.

Consolidates settings from previously separate services (model-management,
and future feature domains) into a single enterprise-grade settings model.

All env vars use UPPER_SNAKE_CASE; pydantic-settings is case-insensitive so
both .env and OS-level vars are accepted.
"""

from typing import Optional

from pydantic import Field
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
    service_name: str
    service_version: str
    api_version: str
    debug: bool = False
    environment: str = "development"

    # ── Database (single primary DB) ──
    database_url: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_host: Optional[str] = None
    postgres_port: Optional[int] = None
    postgres_db: Optional[str] = None

    # Backwards-compatible aliases (model-management-service used APP_DB_*)
    app_db_user: Optional[str] = None
    app_db_password: Optional[str] = None
    app_db_host: Optional[str] = None
    app_db_port: Optional[int] = None
    app_db_name: Optional[str] = None
    core_db_name: Optional[str] = None

    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Secondary auth DB (read-only — used by alert feature for RBAC/tenant lookups) ──
    # All optional; if auth_db_name is None we skip init_auth_database() entirely and the
    # alert feature cannot resolve role/tenant emails. Falls back to primary postgres
    # credentials when the auth_db_* overrides are unset.
    auth_db_url: Optional[str] = None
    auth_db_user: Optional[str] = None
    auth_db_password: Optional[str] = None
    auth_db_host: Optional[str] = None
    auth_db_port: Optional[int] = None
    auth_db_name: Optional[str] = None

    # ── Alert config sync (background reconciliation against Prometheus / Alertmanager) ──
    # All optional; alert_sync_enabled defaults to False so the merged service can run
    # without alerting wired up. Step 8 (lifespan) gates the background task on this flag.
    alert_sync_enabled: bool = False
    sync_interval: int = 60
    default_receiver_emails: Optional[str] = None
    prometheus_url: Optional[str] = None
    prometheus_timeout: float = 10.0
    alertmanager_url: Optional[str] = None
    prometheus_application_alerts_path: Optional[str] = None
    prometheus_infrastructure_alerts_path: Optional[str] = None
    alertmanager_config_path: Optional[str] = None
    # Where Alertmanager forwards every alert for audit logging — typically the
    # merged service's own endpoint. None → no webhook receiver is generated.
    alert_history_webhook_url: Optional[str] = None

    # ── SMTP / SES (Alertmanager email delivery) ──
    # Written into the `global` block of the generated alertmanager.yml. Read from
    # settings (NOT os.getenv) so they load from .env like everything else.
    smtp_smarthost: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_auth_username: Optional[str] = None
    smtp_auth_password: Optional[str] = None

    # ── NER service (used by PII DetectionEngine for AI-based entity extraction) ──
    ner_service_url: str

    # ── LLM service (used by PII /admin/generate-regex to produce regex patterns) ──
    pii_llm_url: str

    # ── Redis ──
    redis_host: str
    redis_port: int
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_timeout: int = 10
    # Cache TTLs
    model_cache_ttl_seconds: int = 3600
    service_cache_ttl_seconds: int = 3600
    metering_cache_ttl_seconds: int = 60
    # Auto-refresh interval exposed to the dashboard (METERING_REFRESH_INTERVAL_SECONDS).
    metering_refresh_interval_seconds: int = 60

    # ── Model management business rules ──
    max_active_versions_per_model: int = 5
    allow_deprecated_model_changes: bool = True

    # ── Endpoint validation ──
    run_inference_test: bool = True
    endpoint_validation_timeout_seconds: float = 15.0
    # Both "lenient" and "strict" accept any non-5xx response (threshold < 500).
    # "strict" (originally < 400) was too aggressive — inference servers
    # legitimately return 400/422 for probe payloads even when healthy.
    # The setting is retained for backwards compatibility; both values behave
    # identically. See endpoint_validator._VALIDATION_MODE_THRESHOLDS.
    endpoint_validation_mode: str = "lenient"
    endpoint_validation_skip_tls_verify: bool = False

    # ── External services ──
    auth_service_url: str = ""
    model_management_url: str = ""

    # ── Logging / Observability ──
    log_level: str = "INFO"
    jaeger_endpoint: Optional[str] = None
    telemetry_enabled: bool = True

    # ── OpenSearch (traces) ──
    opensearch_url: Optional[str] = Field(default=None, description="OpenSearch URL (e.g., http://localhost:9204)")
    opensearch_username: Optional[str] = Field(default=None, description="OpenSearch username")
    opensearch_password: Optional[str] = Field(default=None, description="OpenSearch password")
    opensearch_index: str = Field(default="traces-*", description="OpenSearch traces index pattern")

    # ── Derived helpers ──

    def get_database_url(self) -> str:
        """Build a postgres+asyncpg URL from individual fields if no full URL provided."""
        if self.database_url:
            return self.database_url
        user = self.app_db_user or self.postgres_user
        password = self.app_db_password or self.postgres_password
        host = self.app_db_host or self.postgres_host
        port = self.app_db_port or self.postgres_port
        db = self.core_db_name or self.app_db_name or self.postgres_db
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_auth_db_url(self) -> Optional[str]:
        """Build a postgres+asyncpg URL for the secondary auth_db engine.

        Returns None if auth_db is not configured (alert feature unavailable).
        Each auth_db_* override falls back to the primary postgres value when unset.
        """
        if self.auth_db_url:
            return self.auth_db_url
        db = self.auth_db_name
        if not db:
            return None
        user = self.auth_db_user or self.app_db_user or self.postgres_user
        password = self.auth_db_password or self.app_db_password or self.postgres_password
        host = self.auth_db_host or self.app_db_host or self.postgres_host
        port = self.auth_db_port or self.app_db_port or self.postgres_port
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def get_opensearch_url(self) -> str:
        """Get OpenSearch URL from configuration."""
        return self.opensearch_url


settings = CoreSettings()
