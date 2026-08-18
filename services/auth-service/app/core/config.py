"""
Auth service configuration — self-contained pydantic-settings class.

Reads its own environment variables; no dependency on a shared env library.
"""

import enum
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import ENV_DEVELOPMENT


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
    environment: str = ENV_DEVELOPMENT
    debug: bool = False

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8081
    workers: int = 1
    log_level: str = "INFO"

    # ── Database ──
    database_url: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[SecretStr] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai4iplatform_auth"
    auth_database_url: Optional[str] = None
    auth_db_user: Optional[str] = None
    auth_db_password: Optional[SecretStr] = None
    auth_db_host: Optional[str] = None
    auth_db_port: Optional[int] = None
    # AUTH_SERVICE_DB_NAME takes precedence; AUTH_DB_NAME is the legacy fallback.
    auth_service_db_name: Optional[str] = None
    auth_db_name: Optional[str] = "ai4iplatform_auth"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Default tenant ──
    # Direct portal signups without a tenant_id fall back to this tenant
    # (seeded by auth_service_t_default_tenant_seeder.py).
    default_tenant_org: str = "default organisation"

    # ── Redis ──
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[SecretStr] = None
    redis_db: int = 0
    redis_timeout: int = 10
    redis_max_connections: int = 50

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
    setup_token_expire_hours: int = 48
    api_key_expire_days: int = Field(
        default=365,
        validation_alias=AliasChoices("API_KEY_EXPIRE_DAYS", "APIKEY_EXPIRY"),
    )
    # Negative-cache TTL (seconds) for tokens confirmed absent/ineligible on a
    # Redis miss — short so a later tenant/user reactivation isn't blocked by
    # a stale tombstone.
    invalid_api_key_cache_ttl_seconds: int = 1 * 24 * 60 * 60

    # ── PII field encryption (email / phone at rest) ──
    # Base64- or hex-encoded AES-SIV key (decodes to 32, 48, or 64 bytes; use
    # 64 for AES-256-SIV). Deterministic so encrypted email can be compared
    # directly for duplicate detection. Generate with:
    #   python -c "import base64,os;print(base64.b64encode(os.urandom(64)).decode())"
    pii_encryption_key: Optional[SecretStr] = None

    # ── Password hashing (argon2id) ──
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    argon2_salt_length: int = 16
    # Thread pool max workers for concurrent password hashing/verification
    # Higher values support more concurrent login/register requests (e.g., 50 handles 12+ concurrent users)
    password_hash_max_workers: int = 50

    # ── HTTP Timeouts ──
    # JWKS endpoint timeout for JWT verification
    jwks_http_timeout_seconds: float = 10.0

    # ── OAuth ──
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    oauth_redirect_base_url: Optional[str] = None
    # Comma-separated allowlist of allowed OAuth client redirect URIs.
    # Prevents open redirect / token leakage attacks.
    oauth_allowed_redirect_uris: str = ""
    # OAuth state token TTL (seconds) — bounds time on provider consent screen
    oauth_state_ttl_seconds: int = 600  # 10 minutes
    # OAuth exchange code TTL (seconds) — SPA must POST /exchange within this time
    oauth_exchange_code_ttl_seconds: int = 120  # 2 minutes
    # HTTP request timeout (seconds) for external OAuth provider calls
    oauth_http_timeout_seconds: int = 10

    # ── Guest login (POST /auth/guest/login) — must match guest user email seeded in auth_db ──
    guest_email: Optional[str] = None
    guest_password: Optional[SecretStr] = None

    # ── Email (Amazon SES via SMTP today, swappable to any provider) ──
    # Lib reads these via its own EmailSettings; mirrored here so AuthSettings
    # stays the single source of truth for which env vars this service expects.
    email_provider: str = "smtp"
    email_from: Optional[str] = None
    email_from_name: str = "AI Switch"
    email_reply_to: Optional[str] = None
    email_extra_headers: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[SecretStr] = None
    smtp_use_tls: bool = True
    smtp_timeout: int = 30
    # Product name used in email subject/body copy. Independent of the SMTP
    # From display name (EMAIL_FROM_NAME, read by ai4i_core EmailSettings) so
    # EMAIL_FROM_NAME="COSS Support" does not become "Welcome to COSS Support".
    platform_name: str = "AI Switch"
    setup_link_base_url: Optional[str] = None
    verify_link_base_url: Optional[str] = None
    reset_link_base_url: Optional[str] = None
    # 30 minutes per security spec for password-reset links (vs 48h for setup/verify)
    reset_token_expire_minutes: int = 30
    # Per-email rate limit for /auth/forgot-password
    reset_request_limit_per_hour: int = 3

    # ── External services ──
    platform_core_url: Optional[str] = None
    platform_core_db_name: Optional[str] = None
    # Dedicated credentials for the platform-core Postgres instance.
    # Falls back to the shared POSTGRES_* vars when unset (single-instance deployments).
    platform_core_db_user: Optional[str] = None
    platform_core_db_password: Optional[SecretStr] = None
    platform_core_db_host: Optional[str] = None
    platform_core_db_port: Optional[int] = None

    def get_platform_core_db_url(self) -> Optional[str]:
        if not self.platform_core_db_name:
            return None
        user = self.platform_core_db_user or self.postgres_user or "postgres"
        raw_pw = self.platform_core_db_password or self.postgres_password
        password = raw_pw.get_secret_value() if raw_pw else ""
        host = self.platform_core_db_host or self.postgres_host
        port = self.platform_core_db_port if self.platform_core_db_port is not None else self.postgres_port
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{self.platform_core_db_name}"

    # ── Derived helpers ──

    def get_database_url(self) -> str:
        if self.auth_database_url:
            return self.auth_database_url
        if self.database_url:
            return self.database_url
        user = self.auth_db_user or self.postgres_user or "postgres"
        raw_pw = self.auth_db_password or self.postgres_password
        password = raw_pw.get_secret_value() if raw_pw else ""
        host = self.auth_db_host or self.postgres_host
        port = self.auth_db_port or self.postgres_port
        db = self.auth_service_db_name or self.auth_db_name or self.postgres_db
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_redis_url(self) -> str:
        if self.redis_password:
            pw = self.redis_password.get_secret_value()
            return f"redis://:{pw}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def get_rs256_key_path(self) -> Path:
        return Path(self.rs256_key_directory)

    def get_platform_name(self) -> str:
        """Product name for email subject/body copy. Falls back to AI Switch."""
        return (self.platform_name or "").strip() or "AI Switch"

    def resolve_smtp_from_name(self, email_from_name: str) -> str:
        """SMTP From display name: explicit EMAIL_FROM_NAME, else platform name.

        AuthSettings.email_from_name is only a documented mirror — the provider
        is built from ai4i_core EmailSettings, so callers must pass that value
        in and apply this result when constructing the client.
        """
        return (email_from_name or "").strip() or self.get_platform_name()

    @field_validator("access_token_expire_minutes", "reset_token_expire_minutes")
    @classmethod
    def validate_token_expire_minutes_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Token TTL must be positive")
        return v

    @field_validator("redis_db")
    @classmethod
    def validate_redis_db(cls, v: int) -> int:
        if not 0 <= v <= 15:
            raise ValueError("Redis DB must be 0–15")
        return v

    @field_validator("db_pool_size")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("db_pool_size must be >= 1")
        return v


settings = AuthSettings()

# Hand the PII encryption key to the crypto module so the SQLAlchemy encrypted
# column types can source it from settings (pydantic loads .env into settings,
# not os.environ).
from app.core import pii_crypto  # noqa: E402

pii_crypto.configure_key(
    settings.pii_encryption_key.get_secret_value() if settings.pii_encryption_key else None
)


# ── Role IDs (must match the seeded values in roles table) ───────────
class RoleId:
    ADMIN = 1
    MODERATOR = 2
    GUEST = 3
    USER = 4
    TENANT_ADMIN = 5


# ── Role Names (must match the seeded values in roles table) ──────────
class RoleName(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"
    MODERATOR = "MODERATOR"
    TENANT_ADMIN = "TENANT ADMIN"
    PROGRAM_ADMIN = "PROGRAM ADMIN"
