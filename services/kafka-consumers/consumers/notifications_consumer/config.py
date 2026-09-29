"""Settings specific to notifications_consumer. Nothing here belongs in
bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5).

See skills/notification-kafka-design/notification-kafka-design.md for the
design this consumer implements.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from ai4i_core.kafka.constants import REDIS_KEY_PREFIX
from pydantic import Field
from pydantic_settings import BaseSettings


class Constants:
    # One claim per delivered event_id (SET NX) — catches a Kafka
    # redelivery of an event this consumer already handled.
    DELIVERY_CLAIM_KEY_PREFIX = f"{REDIS_KEY_PREFIX}delivered:"
    DELIVERY_CLAIM_TTL_SECONDS = 7 * 24 * 3600


class Settings(BaseSettings):
    TOPIC_NOTIFICATION: str = Field(
        description="Kafka topic this consumer subscribes to — design doc §10."
    )
    PORTAL_URL: Optional[str] = Field(
        default=None,
        description="Same setting as platform-core-service's settings.portal_url — "
        "the '_portal_line.html' include (email_templates.py) links here when set, "
        "and falls back to unlinked plain text in every rendered email when it isn't.",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
