"""Settings for the one-off backfill, read from the environment (or .env).

Kept in the folder so the feature stays self-contained: the database
connection still comes from pyjob's own settings (bootstrap.config), which
bootstrap.database reads — this only adds the Prometheus and window vars the
backfill needs, and touches nothing shared.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class BackfillSettings(BaseSettings):
    # Prometheus to read the history from. Required to run (export half).
    PROMETHEUS_URL: Optional[str] = None
    PROMETHEUS_TIMEOUT_SECONDS: float = Field(60.0, gt=0)
    # Label carrying the request path on telemetry_obsv_requests_total:
    # "exported_endpoint" on k8s, "endpoint" on a local docker-compose.
    PROMETHEUS_API_PATH_LABEL: str = "exported_endpoint"

    # Window overrides (optional). FROM may not be earlier than the first
    # whole day Prometheus still has; UNTIL defaults to the cut-over (the IST
    # midnight of the day the first usage_events row falls on).
    USAGE_BACKFILL_FROM: Optional[date] = None
    USAGE_BACKFILL_UNTIL: Optional[datetime] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> BackfillSettings:
    return BackfillSettings()
