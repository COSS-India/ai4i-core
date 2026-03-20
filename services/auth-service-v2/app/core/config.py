"""
Auth service configuration — extends ai4icore_env with auth-specific settings.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Auth-service-specific settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ──
    service_name: str = "auth-service"
    service_version: str = "2.0.0"
    api_version: str = "v1"
    environment: str = "development"
    debug: bool = False

    # ── Database ──
    database_url: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai4i_platform"
    auth_database_url: Optional[str] = None
    auth_db_user: Optional[str] = None
    auth_db_password: Optional[str] = None
    auth_db_host: Optional[str] = None
    auth_db_port: Optional[int] = None
    auth_db_name: Optional[str] = None
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Multi-tenant DB ──
    multi_tenant_db_url: Optional[str] = None
    multi_tenant_db_pool_size: int = 20
    multi_tenant_db_max_overflow: int = 10

    # ── Redis ──
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_timeout: int = 10

    # ── RS256 JWT ──
    rs256_key_directory: str = "keys"
    rs256_min_key_count: int = 10
    rs256_active_key_index: int = 0

    # ── JWT strict claims ──
    jwt_issuer: str = "auth-service"
    jwt_audience: Optional[str] = None

    # ── Token expiry ──
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    api_key_expire_days: int = 365

    # ── Password hashing (argon2) ──
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    argon2_hash_length: int = 32
    argon2_salt_length: int = 16
    default_hash_rounds: int = 12

    # ── APISIX ──
    apisix_validation_enabled: bool = True

    # ── CORS ──
    # In production, MUST be set to specific origins (comma-separated).
    # "*" is only allowed in development/testing.
    cors_origins: str = "*"

    # ── Logging / Observability ──
    log_level: str = "INFO"
    jaeger_endpoint: Optional[str] = None
    telemetry_enabled: bool = True

    # ── OAuth ──
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    oauth_redirect_base_url: Optional[str] = None
    # Comma-separated allowlist of allowed OAuth client redirect URIs.
    # Prevents open redirect / token leakage attacks.
    oauth_allowed_redirect_uris: str = ""

    # ── Swagger ──
    swagger_server_url: Optional[str] = None

    # ── Derived helpers ──

    def get_database_url(self) -> str:
        if self.auth_database_url:
            return self.auth_database_url
        if self.database_url:
            return self.database_url
        user = self.auth_db_user or self.postgres_user or "postgres"
        password = self.auth_db_password or self.postgres_password or ""
        host = self.auth_db_host or self.postgres_host
        port = self.auth_db_port or self.postgres_port
        db = self.auth_db_name or self.postgres_db
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def get_rs256_key_path(self) -> Path:
        return Path(self.rs256_key_directory)


settings = AuthSettings()
