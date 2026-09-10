"""Settings specific to notification_consumer. Nothing here belongs in
bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5).

See skills/notification-kafka-design/notification-kafka-design.md for the
design this consumer implements.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
