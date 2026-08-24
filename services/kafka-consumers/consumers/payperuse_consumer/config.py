"""Settings and constants specific to payperuse_consumer.  Nothing here belongs
in bootstrap/config.py — topics, service URLs and domain constants are
per-consumer (ARCHITECTURE.md §3.1/§5)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Constants:
    PPU_PRICING_CACHE_PREFIX = "ppu:svc:"
    PPU_PRICING_CACHE_TTL = 3600
    PPU_BILLED_KEY_PREFIX = "ppu:billed:"
    # Only needs to outlive the redelivery window after a consumer crash/
    # restart (one message, redelivered within seconds of the consumer group
    # rejoining under PER_MESSAGE commit) — 1h is generous headroom for that,
    # not a full day.  The old 86400s TTL made these dedup keys ~100% of
    # Redis's keyspace (2M+ keys, ~40% of maxmemory), risking allkeys-lru
    # evicting unrelated caches (auth:apikey:*, core:service:*) once memory
    # pressure hit.
    PPU_BILLED_KEY_TTL = 3600
    # §7.1 retry ladder: the in-hand Message is retried this many times before
    # being dropped with a CRITICAL log line.
    MAX_ATTEMPTS = 3
    BACKOFF_BASE_S = 1.0
    # §6.4 chunk deadline.  A fraction of KAFKA_MAX_POLL_INTERVAL_MS (300s): the
    # loop stops processing a chunk on reaching this and returns to consume(),
    # which is the only call that resets the poll clock (§6.7).  Sized so that
    # even a chunk of uniformly failing messages cannot overrun the interval.
    CHUNK_DEADLINE_S = 120.0


class PPUSettings(BaseSettings):
    TOPIC_PAY_PER_USE: str = Field(description="Kafka topic carrying OTel spans")
    AUTH_SERVICE_URL: str = Field(description="Base URL of auth-service for internal PPU state updates")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> PPUSettings:
    return PPUSettings()
