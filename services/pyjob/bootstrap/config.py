"""Settings shared by every job.

Database and Redis variables follow auth-service's names: each database has its own
<DB>_USER / _PASSWORD / _HOST / _PORT, falling back to the shared POSTGRES_*
vars when unset (single-instance deployments).

Read through an @lru_cache accessor rather than at import time, so
``python main.py --list`` works without a full environment and a missing
variable fails at run time, after logging is configured.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class PyJobSettings(BaseSettings):
    # ── Shared Postgres fallbacks ──
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[SecretStr] = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # ── Platform-core DB (usage_events, daily_usage, ...) ──
    PLATFORM_CORE_DB_NAME: str = "ai4iplatform_core"
    PLATFORM_CORE_DB_USER: Optional[str] = None
    PLATFORM_CORE_DB_PASSWORD: Optional[SecretStr] = None
    PLATFORM_CORE_DB_HOST: Optional[str] = None
    PLATFORM_CORE_DB_PORT: Optional[int] = None

    # ── Auth DB (tenants, applications, api keys) ──
    # AUTH_SERVICE_DB_NAME takes precedence; AUTH_DB_NAME is the legacy fallback.
    AUTH_SERVICE_DB_NAME: Optional[str] = None
    AUTH_DB_NAME: str = "ai4iplatform_auth"
    AUTH_DB_USER: Optional[str] = None
    AUTH_DB_PASSWORD: Optional[SecretStr] = None
    AUTH_DB_HOST: Optional[str] = None
    AUTH_DB_PORT: Optional[int] = None

    # A job is one short-lived process, so the pools stay small.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5

    # ── Redis ──
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[SecretStr] = None
    REDIS_DB: int = 0
    REDIS_TIMEOUT: int = 10

    # ── Platform-core internal API ──
    PLATFORM_CORE_SERVICE_URL: Optional[str] = Field(
        None, description="Base URL of platform-core-service, for jobs that call its /internal/* endpoints"
    )
    INTERNAL_SERVICE_SHARED_SECRET: Optional[str] = Field(
        None, description="Sent as X-Internal-Service-Token; must match platform-core's setting"
    )
    INTERNAL_HTTP_TIMEOUT_SECONDS: float = Field(
        300.0, description="Per-request timeout for internal calls"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def _db_url(
        self,
        db: str,
        user: Optional[str],
        password: Optional[SecretStr],
        host: Optional[str],
        port: Optional[int],
    ) -> str:
        user = user or self.POSTGRES_USER or "postgres"
        raw_pw = password or self.POSTGRES_PASSWORD
        pw = raw_pw.get_secret_value() if raw_pw else ""
        host = host or self.POSTGRES_HOST
        port = port if port is not None else self.POSTGRES_PORT
        return f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"

    def get_platform_core_db_url(self) -> str:
        return self._db_url(
            self.PLATFORM_CORE_DB_NAME,
            self.PLATFORM_CORE_DB_USER,
            self.PLATFORM_CORE_DB_PASSWORD,
            self.PLATFORM_CORE_DB_HOST,
            self.PLATFORM_CORE_DB_PORT,
        )

    def get_auth_db_url(self) -> str:
        return self._db_url(
            self.AUTH_SERVICE_DB_NAME or self.AUTH_DB_NAME,
            self.AUTH_DB_USER,
            self.AUTH_DB_PASSWORD,
            self.AUTH_DB_HOST,
            self.AUTH_DB_PORT,
        )

    def get_redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            pw = self.REDIS_PASSWORD.get_secret_value()
            return f"redis://:{pw}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> PyJobSettings:
    return PyJobSettings()
