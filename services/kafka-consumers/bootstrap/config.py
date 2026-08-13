"""Infrastructure settings shared by every consumer.

Nothing consumer-specific belongs here — topics, service URLs and domain
constants live in consumers/<name>/config.py (ARCHITECTURE.md §3.1).  A consumer
that never calls auth-service must be able to boot without AUTH_SERVICE_URL set,
which is why neither it nor `Topics` came across from the old service-root
config.py.

Settings are read through @lru_cache accessors rather than instantiated at
import time.  Two reasons: tests/unit/bootstrap must import build_consumer_config
without a full environment, and §3.2's rule that the launcher never imports
config is far easier to keep when merely importing a module cannot explode.
The substance is unchanged — settings are still read once, from the
environment, and still fail loudly, just at run() time when logging is already
configured and the consumer name is known.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Optional

from ai4i_core.logging import get_logger
from confluent_kafka import KafkaError
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

logger = get_logger(__name__)


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
    # Inert: ai4i_core.bootstrap.init_redis exposes no pool-size knob at 1.0.2.
    # Kept so the deployment's .env keeps validating; remove when the lib grows one.
    REDIS_MAX_CONNECTIONS: int = Field(
        50, description="Redis connection pool max size (currently inert)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_redis_url(self) -> str:
        # The logical db index belongs in the URL.  Do NOT reach for
        # init_redis(..., redis_db=...) as auth-service does — that kwarg does
        # not exist at the pinned ai4i-core 1.0.2 and would raise TypeError.
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class KafkaSettings(BaseSettings):
    """Broker connection and poll settings.

    The group id is NOT here — it is a hardcoded constant in each consumer's
    main.py (§5), and a parameter to build_consumer_config below.
    """

    KAFKA_SERVER: str = Field(description="Bootstrap broker address (host:port)")
    KAFKA_AUTO_OFFSET_RESET: str = Field(
        "error",
        description=(
            "Offset reset policy when there is no valid committed offset. "
            "'error' surfaces the reset as an _AUTO_OFFSET_RESET entry instead of "
            "silently replaying the topic and mass double-billing — §10."
        ),
    )
    KAFKA_ENABLE_AUTO_COMMIT: bool = Field(
        False,
        description="Must stay false; consumers commit explicitly after each handler succeeds",
    )
    KAFKA_SESSION_TIMEOUT_MS: int = Field(
        30_000, description="Heartbeat window before the broker declares us dead"
    )
    KAFKA_MAX_POLL_INTERVAL_MS: int = Field(
        300_000, description="Max gap between fetches before the group evicts us"
    )
    KAFKA_POLL_TIMEOUT_S: float = Field(
        1.0, description="Seconds one consume() call may block; also bounds shutdown latency"
    )
    KAFKA_BATCH_SIZE: int = Field(
        1,
        ge=1,
        description=(
            "Messages requested per consume() call.  DEFAULT 1 — above 1 this "
            "opens an in-flight window during rebalances (§6.4) and re-enables "
            "librdkafka's batch-API hazard (§11).  Raising it requires the "
            "write-time guard (§8.2) and reconciliation (§7.5) to be live."
        ),
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @field_validator("KAFKA_ENABLE_AUTO_COMMIT")
    @classmethod
    def _reject_auto_commit(cls, v: bool) -> bool:
        # build_consumer_config hardcodes False.  Fail loudly rather than
        # silently ignoring a deployment that asked for auto-commit.
        if v:
            raise ValueError(
                "KAFKA_ENABLE_AUTO_COMMIT=true is not supported: offsets are "
                "committed explicitly after each handler succeeds (§6.1)."
            )
        return v


@lru_cache(maxsize=1)
def get_kafka_settings() -> KafkaSettings:
    return KafkaSettings()


@lru_cache(maxsize=1)
def get_db_settings() -> DatabaseSettings:
    return DatabaseSettings()


@lru_cache(maxsize=1)
def get_redis_settings() -> RedisSettings:
    return RedisSettings()


class BrokerErrorReporter:
    """error_cb for librdkafka.  Called on librdkafka's own thread — must not
    block and must not touch the event loop.

    Without an error_cb, _TRANSPORT / _ALL_BROKERS_DOWN never reach the
    application: the binding registers a default that discards them.  The
    consumer can then sit disconnected indefinitely while consume() returns [],
    the loop spins, and the Docker healthcheck sees a live process (§3.1).

    Rate-limited PER ERROR CODE: measured against an unreachable broker,
    librdkafka fires 32 callbacks in ~1.5s, alternating _TRANSPORT and
    _ALL_BROKERS_DOWN.  Deduping on "the last code" would therefore suppress
    nothing at all.
    """

    def __init__(self, min_interval_s: float = 60.0) -> None:
        self._min_interval = min_interval_s
        self._last_logged: dict[int, float] = {}

    def __call__(self, err: KafkaError) -> None:
        now = time.monotonic()  # NOT loop.time() — this runs on another thread
        code = err.code()
        previous = self._last_logged.get(code)
        if previous is not None and now - previous < self._min_interval:
            return
        self._last_logged[code] = now
        level = logger.critical if err.fatal() else logger.error
        level("Broker error | code=%s fatal=%s: %s", err.name(), err.fatal(), err.str())


def build_consumer_config(group_id: str, settings: KafkaSettings | None = None) -> dict:
    """Translate KafkaSettings into a librdkafka config dict.

    group_id is a PARAMETER, never a setting (§3.1/§5).
    """
    s = settings or get_kafka_settings()
    return {
        "bootstrap.servers": s.KAFKA_SERVER,
        "group.id": group_id,
        "auto.offset.reset": s.KAFKA_AUTO_OFFSET_RESET,
        "session.timeout.ms": s.KAFKA_SESSION_TIMEOUT_MS,
        "max.poll.interval.ms": s.KAFKA_MAX_POLL_INTERVAL_MS,

        # ── Fixed below: correctness, not tuning (§3.1).  Do not promote to settings. ──
        # Nothing is committed on a timer behind our back.
        "enable.auto.commit": False,
        # THE important one: left at its default (true) a fetch marks a message
        # committable the instant it is returned — including ones whose handler
        # later raised — so any commit would advance past a failed message (§6.1).
        "enable.auto.offset.store": False,
        # Incremental rebalancing: only the partitions that must move are revoked,
        # instead of stop-the-world for the whole group (§6.5).
        "partition.assignment.strategy": "cooperative-sticky",
        "error_cb": BrokerErrorReporter(),
    }
