"""Settings specific to notification_consumer. Nothing here belongs in
bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5).

DUMMY SCAFFOLD (AI4IDS-3026): this consumer has no processing logic yet —
see main.py's module docstring. TOPIC_NOTIFICATION exists so the process can
boot and subscribe to something; it is not read by any handler today.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TOPIC_NOTIFICATION: str = Field(
        description="Kafka topic this consumer subscribes to. Placeholder until "
        "the notification.events topic is finalised in the updated design."
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
