"""SUPERSEDED by bootstrap/config.py — kept only until payperuse_consumer moves.

This module is still imported by consumers/payperuse_consumer/{main,handler,
_billing}.py, which have not been migrated yet, so it cannot be deleted.  Do not
add anything to it and do not import it from new code.

The two modules deliberately DISAGREE, so be sure which one you are reading:

  * KAFKA_AUTO_OFFSET_RESET defaults to 'earliest' here and 'error' in
    bootstrap/config.py.  'error' is the intended value (ARCHITECTURE.md §10) —
    'earliest' silently replays the whole topic and re-bills every span in
    retention when an offset ages out.  Changing it here is NOT a safe drive-by:
    it would stop the current consumer starting, and the group-id cutover
    runbook has to run first.
  * settings is instantiated at import time here; bootstrap/config.py reads
    settings lazily through @lru_cache accessors (§3.2).
  * Topics and AUTH_SERVICE_URL do not move to bootstrap/config.py at all —
    they are per-consumer (§3.1/§5).

Deleted by IMPLEMENTATION_PLAN.md Phase 5, together with the consumer rewrite.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Constants:
    """
    Constants That will be used as class variables.
    All
    """
    # PPU Settings constants
    PPU_PRICING_CACHE_PREFIX = "ppu:svc:"
    PPU_PRICING_CACHE_TTL = 3600
    PPU_BILLED_KEY_PREFIX = "ppu:billed:"
    # Only needs to outlive the redelivery window after a consumer crash/
    # restart (at most COMMIT_BATCH_SIZE uncommitted messages, redelivered
    # within seconds of the consumer group rejoining) — 1h is generous
    # headroom for that, not a full day. At high billing volume the old
    # 86400s TTL made these dedup keys ~100% of Redis's keyspace (2M+ keys,
    # ~40% of maxmemory), risking allkeys-lru evicting unrelated caches
    # (auth:apikey:*, core:service:*) once memory pressure hit.
    PPU_BILLED_KEY_TTL = 3600


class Topics(BaseSettings):
    TOPIC_PAY_PER_USE: str = Field(
        description="Kafka topic for pay-per-use usage events",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""
    POSTGRES_USER: str = Field(description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(description="PostgreSQL password")
    POSTGRES_HOST: str = Field(description="PostgreSQL host")
    POSTGRES_PORT: int = Field(5432, description="PostgreSQL port")
    PLATFORM_CORE_DB: str = Field(description="Database name for the platform core service")
    DB_POOL_SIZE: int = Field(20, description="SQLAlchemy connection pool size")
    DB_MAX_OVERFLOW: int = Field(10, description="SQLAlchemy max overflow connections")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_database_url(self, db: str) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{db}"
        )


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    REDIS_HOST: str = Field(description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password")
    REDIS_DB: int = Field(0, description="Redis logical database index (0–15)")
    REDIS_TIMEOUT: int = Field(10, description="Redis socket timeout in seconds")
    REDIS_MAX_CONNECTIONS: int = Field(50, description="Redis connection pool max size")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class KafkaSettings(BaseSettings):
    """Kafka connection settings loaded from environment variables."""

    KAFKA_SERVER: str = Field(
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
    AUTH_SERVICE_URL: str = Field(
        description="Base URL of auth-service for internal PPU state updates",
    )

    topics: Topics = Field(default_factory=Topics)
    db_settings: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis_settings: RedisSettings = Field(default_factory=RedisSettings)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = KafkaSettings()


def build_consumer_config(group_id: str, s: KafkaSettings) -> dict:
    """Translate KafkaSettings into a confluent-kafka Consumer config dict."""
    return {
        "bootstrap.servers": s.KAFKA_SERVER,
        "group.id": group_id,
        "auto.offset.reset": s.KAFKA_AUTO_OFFSET_RESET,
        "enable.auto.commit": s.KAFKA_ENABLE_AUTO_COMMIT,
        "session.timeout.ms": s.KAFKA_SESSION_TIMEOUT_MS,
        "max.poll.interval.ms": s.KAFKA_MAX_POLL_INTERVAL_MS,
    }
