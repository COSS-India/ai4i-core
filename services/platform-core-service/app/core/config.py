"""
Core Service configuration.

Consolidates settings from previously separate services (model-management,
and future feature domains) into a single enterprise-grade settings model.

All env vars use UPPER_SNAKE_CASE; pydantic-settings is case-insensitive so
both .env and OS-level vars are accepted.
"""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai4i_core.ppu import get_inference_types


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

    # ── Task-type enablement ──
    # Comma-separated allowlist of task types this deployment serves (yaml `name`
    # form, e.g. "llm,nmt,asr"). platform-core is the ONLY reader; every other
    # surface derives from it via the enabled set. Required — an unset or unknown
    # value fails boot (fail-fast). See docs/design/ENABLED_TASK_TYPES.md.
    enabled_task_types: str = Field(..., description="Comma-separated enabled task types")

    @field_validator("enabled_task_types")
    @classmethod
    def _validate_enabled_task_types(cls, v: str) -> str:
        # Normalize like task_type_policy._normalize (case + underscore→hyphen) so
        # operators can write any spelling; canonical is the yaml lower-hyphen name.
        def _norm(s: str) -> str:
            return s.strip().lower().replace("_", "-")
        known = {_norm(t["name"]) for t in get_inference_types()}
        provided = {_norm(s) for s in v.split(",") if s.strip()}
        if not provided:
            raise ValueError(
                "ENABLED_TASK_TYPES must list at least one task type "
                f"(valid names: {sorted(known)})"
            )
        unknown = provided - known
        if unknown:
            raise ValueError(
                f"ENABLED_TASK_TYPES contains unknown task types: {sorted(unknown)}. "
                f"Valid names: {sorted(known)}"
            )
        return v

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8095
    workers: int = 1

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
    # Label carrying the HTTP path on telemetry_obsv_requests_total (and related
    # metrics). Scraped via a K8s Prometheus Operator ServiceMonitor, the target's
    # own "endpoint" label collides with the ServiceMonitor's port-name label of
    # the same name, so Prometheus relabels the original to "exported_endpoint".
    # Local docker-compose Prometheus uses plain static_configs (no ServiceMonitor,
    # no collision), so the metric keeps its literal "endpoint" label there —
    # override PROMETHEUS_API_PATH_LABEL=endpoint in local .env to match.
    prometheus_api_path_label: str = "exported_endpoint"
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
    service_cache_ttl_seconds: int = 300
    metering_cache_ttl_seconds: int = 60
    ppu_tier_cache_ttl_seconds: int = 600
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
    telemetry_enabled: bool = True

    # ── OpenSearch (traces) ──
    opensearch_url: Optional[str] = Field(
        default=None, description="OpenSearch URL (e.g., http://localhost:9204)"
    )
    opensearch_username: Optional[str] = Field(
        default=None, description="OpenSearch username"
    )
    opensearch_password: Optional[str] = Field(
        default=None, description="OpenSearch password"
    )
    opensearch_index: str = Field(
        default="traces-*", description="OpenSearch traces index pattern"
    )

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
        password = (
            self.auth_db_password or self.app_db_password or self.postgres_password
        )
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
