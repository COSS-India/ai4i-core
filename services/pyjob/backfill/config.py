"""Settings for the one-off backfill, read from the environment (or a .env in
the current directory).

The database connection comes from pyjob's own settings (bootstrap.config);
these are only what the backfill adds.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class BackfillSettings(BaseSettings):
    # Prometheus to read the history from.
    PROMETHEUS_URL: Optional[str] = None
    PROMETHEUS_TIMEOUT_SECONDS: float = Field(60.0, gt=0)
    # Label carrying the request path on telemetry_obsv_requests_total:
    # "exported_endpoint" on k8s, "endpoint" on a local docker-compose.
    PROMETHEUS_API_PATH_LABEL: str = "exported_endpoint"

    # The IST days to backfill, both inclusive (YYYY-MM-DD). BACKFILL_FROM must
    # be a day Prometheus still has from its start; BACKFILL_TO must end before
    # usage_events begins.
    BACKFILL_FROM: Optional[date] = None
    BACKFILL_TO: Optional[date] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> BackfillSettings:
    return BackfillSettings()
