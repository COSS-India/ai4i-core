from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class KafkaSettings(BaseSettings):
    """Kafka connection settings loaded from environment variables."""

    KAFKA_SERVER: str = Field(
        "localhost:9093",
        description="Bootstrap broker address (host:port)",
    )
    KAFKA_AUTO_OFFSET_RESET: str = Field(
        "earliest",
        description="Offset reset policy when no committed offset exists: 'earliest' or 'latest'",
    )
    KAFKA_ENABLE_AUTO_COMMIT: bool = Field(
        False,
        description="Disable auto-commit so BaseKafkaConsumer commits explicitly after handle_message()",
    )
    KAFKA_SESSION_TIMEOUT_MS: int = Field(
        30_000,
        description="Broker marks consumer dead if no heartbeat within this window (ms)",
    )
    KAFKA_MAX_POLL_INTERVAL_MS: int = Field(
        300_000,
        description="Max time between consecutive poll() calls before a rebalance is triggered (ms)",
    )
    KAFKA_POLL_TIMEOUT_S: float = Field(
        1.0,
        description="Seconds to block on each Consumer.poll() call",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def build_consumer_config(group_id: str, settings: KafkaSettings) -> dict:
    """Translate KafkaSettings into a confluent-kafka Consumer config dict."""
    return {
        "bootstrap.servers": settings.KAFKA_SERVER,
        "group.id": group_id,
        "auto.offset.reset": settings.KAFKA_AUTO_OFFSET_RESET,
        "enable.auto.commit": settings.KAFKA_ENABLE_AUTO_COMMIT,
        "session.timeout.ms": settings.KAFKA_SESSION_TIMEOUT_MS,
        "max.poll.interval.ms": settings.KAFKA_MAX_POLL_INTERVAL_MS,
    }