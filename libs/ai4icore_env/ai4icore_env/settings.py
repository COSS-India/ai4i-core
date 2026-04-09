"""
Centralized application configuration using Pydantic Settings.

Covers all shared environment variables across the project.
Environment variables always take precedence over defaults.

Fields follow this convention:
- Credentials (passwords, secrets, tokens, API keys): Optional[str] = None
  → MUST be set via .env or environment variables
- Infrastructure defaults (hostnames, ports, DB names, URLs): str/int with defaults
  → Safe defaults for Docker Compose; override via .env as needed
- Operational config (timeouts, pool sizes, booleans): typed with defaults
  → Sensible defaults that work out of the box
"""

from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Shared PostgreSQL ──
    postgres_user: Optional[str] = None          # credential
    postgres_password: Optional[str] = None      # credential
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_db: str = ""

    # ── Direct URL overrides (take precedence when set) ──
    database_url: Optional[str] = None
    multi_tenant_db_url: Optional[str] = None
    auth_database_url: Optional[str] = None

    # ── Component-based overrides (multi-tenant-feature, model-management) ──
    app_db_user: Optional[str] = None            # credential – falls back to postgres_user
    app_db_password: Optional[str] = None        # credential – falls back to postgres_password
    app_db_host: Optional[str] = None            # falls back to postgres_host
    app_db_port: Optional[int] = None            # falls back to postgres_port
    app_db_name: Optional[str] = None

    auth_db_user: Optional[str] = None           # credential – falls back to postgres_user
    auth_db_password: Optional[str] = None       # credential – falls back to postgres_password
    auth_db_host: Optional[str] = None           # falls back to postgres_host
    auth_db_port: Optional[int] = None           # falls back to postgres_port
    auth_db_name: Optional[str] = None           # falls back to postgres_db

    # ── Database names ──
    multi_tenant_db_name: str = ""
    ai4i_platform_db_name: str = ""

    # ── Pool settings ──
    db_pool_size: int = 20
    db_max_overflow: int = 10
    multi_tenant_db_pool_size: int = 20
    multi_tenant_db_max_overflow: int = 10

    # ── Redis ──
    redis_host: str = ""
    redis_port: int = 6379
    redis_password: Optional[str] = None         # credential
    redis_db: int = 0
    redis_timeout: int = 10

    # ── JWT Authentication ──
    jwt_secret_key: Optional[str] = None         # credential
    jwt_refresh_secret_key: Optional[str] = None # credential
    jwt_issuer: Optional[str] = None
    jwt_issuer_url: Optional[str] = None
    jwt_audience: Optional[str] = None
    jwks_url: Optional[str] = None
    jwks_path: Optional[str] = None
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_token_expire_hours: int = 24

    # ── Elasticsearch ──
    elasticsearch_url: Optional[str] = None
    elasticsearch_username: Optional[str] = None # credential
    elasticsearch_password: Optional[str] = None # credential

    # ── OpenSearch ──
    opensearch_url: Optional[str] = None
    opensearch_username: Optional[str] = None    # credential
    opensearch_password: Optional[str] = None    # credential

    # ── InfluxDB ──
    influxdb_url: Optional[str] = None
    influxdb_token: Optional[str] = None         # credential
    influxdb_org: Optional[str] = None
    influxdb_bucket: Optional[str] = None

    # ── Kafka ──
    kafka_bootstrap_servers: str = ""
    kafka_log_topic: str = ""
    kafka_topic_config_updates: str = ""
    use_kafka_logging: bool = False

    # ── Service identity ──
    service_name: str = ""
    service_version: str = "1.0.0"
    service_port: int = 8080
    service_host: Optional[str] = None
    service_public_url: Optional[str] = None
    service_instance_id: Optional[str] = None
    environment: str = "development"
    env: Optional[str] = None
    log_level: str = "INFO"
    root_log_level: Optional[str] = None

    # ── Rate limiting ──
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    try_it_limit: int = 5
    try_it_ttl_seconds: int = 3600

    # ── Triton inference ──
    triton_endpoint: Optional[str] = None
    triton_api_key: Optional[str] = None         # credential
    triton_timeout: float = 300.0
    triton_endpoint_cache_ttl: int = 300

    # ── Per-service Triton endpoints (seeded into model_management_db) ──
    triton_endpoint_asr: str = ""
    triton_endpoint_tts: str = ""
    triton_endpoint_nmt: str = ""
    triton_endpoint_llm: str = ""
    triton_endpoint_transliteration: str = ""
    triton_endpoint_langdetect: str = ""
    triton_endpoint_speaker_diarization: str = ""
    triton_endpoint_audio_langdetect: str = ""
    triton_endpoint_lang_diarization: str = ""
    triton_endpoint_ocr: str = ""
    triton_endpoint_ner: str = ""

    # ── Downstream service URLs (must be set via .env) ──
    api_gateway_url: str = ""
    auth_service_url: str = ""
    config_service_url: str = ""
    metrics_service_url: str = ""
    telemetry_service_url: str = ""
    alerting_service_url: str = ""
    dashboard_service_url: str = ""
    asr_service_url: str = ""
    tts_service_url: str = ""
    nmt_service_url: str = ""
    transliteration_service_url: str = ""
    language_detection_service_url: str = ""
    model_management_service_url: str = ""
    pipeline_service_url: str = ""
    ocr_service_url: str = ""
    ner_service_url: str = ""
    pii_service_url: str = ""
    pii_redact_timeout: float = 20.0
    speaker_diarization_service_url: str = ""
    language_diarization_service_url: str = ""
    audio_lang_detection_service_url: str = ""
    multi_tenant_service_url: str = ""
    alert_management_service_url: str = ""
    alert_config_sync_service_url: str = ""
    smr_service_url: str = ""
    llm_service_url: str = ""
    policy_engine_url: str = ""
    request_profiler_service_url: str = ""
    simple_ui_url: str = ""
    frontend_url: str = ""
    llm_translate_api_url: str = ""
    swagger_server_url: str = ""

    # ── Model Management ──
    model_management_service_api_key: Optional[str] = None  # credential
    model_management_api_key: Optional[str] = None          # credential
    model_management_cache_ttl: int = 300
    max_active_versions_per_model: int = 5
    allow_deprecated_model_changes: bool = True

    # ── Multi-tenant ──
    multi_tenant_enabled: bool = True
    multi_tenant_service_name: str = ""
    multi_tenant_service_port: str = ""
    multi_tenant_service_scheme: str = ""
    tenant_paths: Optional[str] = None

    # ── HTTP Timeouts ──
    pipeline_http_timeout: float = 120.0
    api_gateway_timeout: float = 10.0
    policy_service_http_timeout: float = 10.0

    # ── Auth / API key ──
    auth_enabled: Optional[str] = None
    auth_http_timeout: float = 5.0
    allow_anonymous_access: bool = False
    require_api_key: Optional[str] = None
    api_key_cache_ttl: int = 300
    api_key_encryption_key: Optional[str] = None  # credential

    # ── SMTP / Email ──
    smtp_auth_username: Optional[str] = None      # credential
    smtp_auth_password: Optional[str] = None      # credential
    smtp_smarthost: Optional[str] = None
    smtp_from: Optional[str] = None
    sendgrid_api_key: Optional[str] = None        # credential
    from_email: str = ""
    default_receiver_emails: str = ""
    login_url: str = ""
    email_verification_link: str = ""
    # Multi-tenant email verification token expiry (used by multi-tenant-feature)
    email_verification_token_expire_minutes: int = 15
    email_verification_resend_min_interval_seconds: int = 60
    email_verification_resend_max_per_hour: int = 5
    email_verification_resend_max_per_day: int = 10

    # ── OAuth ──
    google_client_id: Optional[str] = None        # credential
    google_client_secret: Optional[str] = None    # credential
    google_redirect_uri: str = ""
    github_client_id: Optional[str] = None        # credential

    # ── Unleash / Feature Flags ──
    unleash_url: str = ""
    unleash_api_token: Optional[str] = None       # credential
    unleash_environment: str = "development"
    unleash_app_name: str = ""
    unleash_instance_id: str = ""
    unleash_refresh_interval: int = 15
    unleash_metrics_interval: int = 60
    unleash_disable_metrics: bool = False
    unleash_auto_sync_on_startup: bool = False
    unleash_auto_sync_enabled: bool = False
    unleash_sync_interval: int = 60
    unleash_sync_environments: str = ""
    feature_flag_cache_ttl: int = 300
    feature_flag_kafka_topic: str = ""

    # ── ZooKeeper ──
    zookeeper_hosts: str = ""
    zookeeper_base_path: str = ""
    zookeeper_session_timeout: int = 30
    zookeeper_connection_timeout: int = 10

    # ── Jaeger / Tracing ──
    jaeger_endpoint: str = ""
    jaeger_query_url: str = ""
    jaeger_query_base_path: str = ""
    jaeger_ui_url: str = ""

    # ── Prometheus / Alerting ──
    prometheus_url: str = ""
    prometheus_application_alerts_path: str = ""
    prometheus_infrastructure_alerts_path: str = ""
    alertmanager_url: str = ""
    alertmanager_config_path: str = ""
    alert_sync_enabled: bool = False
    sync_interval: int = 60

    # ── Log filtering ──
    exclude_health_logs: bool = False
    exclude_metrics_logs: bool = False
    exclude_options_logs: bool = False
    allowed_log_levels: str = ""
    min_log_level: str = "INFO"
    include_4xx_logs: bool = False

    # ── Request logging ──
    logging_plugin_enabled: bool = True
    request_logging_middleware_enabled: bool = True
    request_log_include_paths: str = ""

    # ── Telemetry / Observability ──
    telemetry_enabled: bool = True
    telemetry_filter_http_spans: bool = False
    telemetry_instrument_fastapi: bool = True
    telemetry_instrument_httpx: bool = False
    telemetry_instrument_requests: bool = False
    telemetry_ip_capture_enabled: bool = False
    correlation_middleware_enabled: bool = True
    correlation_header_name: str = ""

    # ── Observability util ──
    observe_util_enabled: bool = False
    observe_util_debug: bool = False
    observe_util_health_path: str = "/health"
    observe_util_metrics_path: str = "/metrics"
    observe_util_metrics_update_interval: int = 60
    observe_util_system_metrics_interval: int = 30
    observe_util_collect_system_metrics: bool = True
    observe_util_collect_gpu_metrics: bool = False
    observe_util_collect_db_metrics: bool = False
    observe_util_max_completed_requests: int = 1000
    observe_util_response_time_target: float = 1.0
    observe_util_throughput_target: float = 100.0
    observe_util_availability_target: float = 99.9
    observe_util_apps: str = ""
    observe_util_customers: str = ""

    # ── Health check ──
    health_check_timeout: int = 5
    health_check_additional_endpoints: str = ""
    health_check_max_retries: int = 3
    health_check_initial_retry_delay: float = 1.0
    health_check_max_retry_delay: float = 30.0
    health_check_retry_backoff: float = 2.0
    service_health_check_enabled: bool = True
    service_health_check_interval: int = 30

    # ── CORS ──
    cors_origins: str = "*"

    # ── Misc service config ──
    streamlit_port: str = ""
    port: int = 8080
    reload: bool = False
    bypass_cache: bool = False
    smr_enabled: bool = False
    streaming_response_frequency_ms: int = 100
    default_service_timeout_seconds: float = 30.0
    ner_service_timeout_seconds: float = 30.0

    # ── API Gateway service registry / load balancer ──
    service_registry_ttl: int = 300
    max_consecutive_failures: int = 3
    load_balancer_algorithm: str = ""

    # ── Migration-specific (standalone scripts) ──
    migration_db_host: str = ""
    migration_db_port: int = 5434
    restore_db_host: str = ""
    restore_db_port: int = 5434

    # ── Test ──
    test_database_url: Optional[str] = None
    test_redis_url: Optional[str] = None

    @model_validator(mode="after")
    def _resolve_fallbacks(self) -> "AppEnv":
        """Ensure component-based fields fall back to shared postgres credentials."""
        if self.app_db_user is None:
            self.app_db_user = self.postgres_user
        if self.app_db_password is None:
            self.app_db_password = self.postgres_password
        if self.app_db_host is None:
            self.app_db_host = self.postgres_host
        if self.app_db_port is None:
            self.app_db_port = self.postgres_port

        if self.auth_db_user is None:
            self.auth_db_user = self.postgres_user
        if self.auth_db_password is None:
            self.auth_db_password = self.postgres_password
        if self.auth_db_host is None:
            self.auth_db_host = self.postgres_host
        if self.auth_db_port is None:
            self.auth_db_port = self.postgres_port
        if self.auth_db_name is None:
            self.auth_db_name = self.postgres_db
        return self

    # ── URL builders ──

    def _build_url(self, user: str, password: str, host: str, port: int, db_name: str) -> str:
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"

    def get_database_url(self, db_name: Optional[str] = None) -> str:
        """
        Returns the primary database URL.

        Priority: DATABASE_URL env var > built from POSTGRES_* components.
        Pass db_name to override the database name when building from components.
        """
        if self.database_url and db_name is None:
            return self.database_url
        return self._build_url(
            self.postgres_user,
            self.postgres_password,
            self.postgres_host,
            self.postgres_port,
            db_name or self.postgres_db,
        )

    def get_multi_tenant_db_url(self) -> str:
        """Returns the multi-tenant database URL."""
        if self.multi_tenant_db_url:
            return self.multi_tenant_db_url
        return self._build_url(
            self.postgres_user,
            self.postgres_password,
            self.postgres_host,
            self.postgres_port,
            self.multi_tenant_db_name,
        )

    def get_auth_database_url(self) -> str:
        """Returns the auth database URL."""
        if self.auth_database_url:
            return self.auth_database_url
        return self._build_url(
            self.auth_db_user,
            self.auth_db_password,
            self.auth_db_host,
            self.auth_db_port,
            self.auth_db_name,
        )

    def get_app_database_url(self) -> str:
        """Returns the app database URL."""
        return self._build_url(
            self.app_db_user,
            self.app_db_password,
            self.app_db_host,
            self.app_db_port,
            self.app_db_name or self.postgres_db,
        )

    def get_redis_url(self) -> str:
        """Returns the Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


app_env = AppEnv()
