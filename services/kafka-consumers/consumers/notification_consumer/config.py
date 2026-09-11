"""Settings specific to notification_consumer. Nothing here belongs in
bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5).

See skills/notification-kafka-design/notification-kafka-design.md for the
design this consumer implements.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Constants:
    # Design doc §8: "read from an in-memory cache that refreshes from the
    # database once an hour." Settings change rarely (an Adopter Admin PATCH),
    # so this trades a bounded staleness window for not hitting Postgres on
    # every single Kafka message.
    CONFIG_CACHE_TTL_SECONDS = 3600


class Settings(BaseSettings):
    TOPIC_NOTIFICATION: str = Field(
        description="Kafka topic this consumer subscribes to — design doc §10."
    )
    AUTH_SERVICE_DB: str = Field(
        default="ai4iplatform_auth",
        description="Database name for the second, named connection this consumer "
        "opens (main.py, bootstrap.lifecycle.add_database) so recipients.py can "
        "resolve who holds which role for a tenant. Same Postgres instance/"
        "credentials as PLATFORM_CORE_DB — only the database name differs.",
    )
    PII_ENCRYPTION_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Decrypts users.email in ai4iplatform_auth (recipients.py / "
        "pii_crypto.py) — must be the exact same value auth-service's own "
        "PII_ENCRYPTION_KEY is set to. Handed to pii_crypto.configure_key() at "
        "startup (main.py); reading it here rather than via bare os.getenv is "
        "what makes it actually load from this consumer's .env — pydantic-settings "
        "loads .env into this Settings object, not into os.environ.",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
